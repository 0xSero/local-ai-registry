// Exact immutable FP8 row retrieval; bounded direct-mapped RAM cache.
// v2 (2026-09-18): cache misses of one lookup are read concurrently by a thread pool
// instead of two serial QD1 O_DIRECT preads per row. ABI and cache layout unchanged.
// No CUDA calls in the callback: suitable for cudaLaunchHostFunc graph nodes.
#include <algorithm>
#include <atomic>
#include <condition_variable>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <mutex>
#include <string>
#include <sys/mman.h>
#include <sys/stat.h>
#include <thread>
#include <unistd.h>
#include <vector>

struct Store {
  int fd;
  uint64_t rows, weight_offset, scale_offset, slots, row_lo, row_hi;
  uint8_t *cache;
  uint64_t *keys;
  uint8_t *resident = nullptr;
  size_t resident_size = 0;
  int scale_fd = -1;
  uint8_t *packed_scale = nullptr;
  size_t packed_size = 0;
  uint8_t scale_lut[8];
  std::mutex locks[256];
  std::atomic<uint64_t> hits{0}, misses{0}, reads{0};
};
struct Work {
  Store *store;
  const int64_t *ids;
  uint8_t *weights, *scales;
  uint64_t count;
};

static void fail(const char *reason) {
  std::fprintf(stderr, "Engram retrieval failed: %s (errno=%d)\n", reason, errno);
  std::abort(); // Never allow a generation to continue with missing/stale rows.
}

static void read_bytes(Store *s, uint64_t offset, uint8_t *out, size_t length) {
  if (s->packed_scale && offset >= s->scale_offset && offset < s->scale_offset + s->rows * 8) {
    if (length != 8 || (offset - s->scale_offset) % 8) fail("Invalid scale read");
    const uint8_t *p = s->packed_scale + 8 + ((offset - s->scale_offset) / 8) * 3;
    const uint32_t word = uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16);
    for (int i = 0; i < 8; ++i) out[i] = s->scale_lut[(word >> (3*i)) & 7];
    return;
  }
  if (s->resident) {
    std::memcpy(out, s->resident + offset, length);
    return;
  }
  alignas(4096) uint8_t page[8192];
  const uint64_t base = offset & ~uint64_t(4095);
  const size_t delta = offset - base;
  const size_t requested = ((delta + length + 4095) / 4096) * 4096;
  ssize_t got;
  do { got = pread(s->fd, page, requested, base); } while (got < 0 && errno == EINTR);
  if (got < 0 || size_t(got) < delta + length) fail("short or failed direct read");
  std::memcpy(out, page + delta, length);
  s->reads.fetch_add(1, std::memory_order_relaxed);
}

static void map_packed_scale(Store *s, const char *path, uint64_t rows) {
  const std::string packed_path = std::string(path) + ".scale3";
  s->scale_fd = open(packed_path.c_str(), O_RDONLY | O_CLOEXEC);
  struct stat packed_stat;
  if (s->scale_fd < 0 || fstat(s->scale_fd, &packed_stat) || uint64_t(packed_stat.st_size) != 8 + rows*3)
    fail("Invalid lossless scale file");
  s->packed_size = packed_stat.st_size;
  s->packed_scale = static_cast<uint8_t *>(mmap(nullptr,s->packed_size,PROT_READ,MAP_SHARED,s->scale_fd,0));
  if (s->packed_scale == MAP_FAILED) fail("Scale mapping");
  std::memcpy(s->scale_lut,s->packed_scale,8);
}

extern "C" Store *row_store_open(const char *path, uint64_t rows,
                                 uint64_t woff, uint64_t soff, uint64_t budget) {
  auto *s = new Store;
  const char *mode = std::getenv("OFFLOAD_MODE");
  const bool ram = mode && std::strcmp(mode, "ram") == 0;
  s->fd = open(path, O_RDONLY | O_CLOEXEC | (ram ? 0 : O_DIRECT));
  if (s->fd < 0) { delete s; return nullptr; }
  struct stat statbuf;
  if (fstat(s->fd, &statbuf) || woff > uint64_t(statbuf.st_size) ||
      soff > uint64_t(statbuf.st_size) || rows > (uint64_t(statbuf.st_size)-woff)/128 ||
      rows > (uint64_t(statbuf.st_size)-soff)/8) fail("invalid table extent");
  if (ram) {
    s->resident_size = statbuf.st_size;
    s->resident = static_cast<uint8_t *>(mmap(nullptr,s->resident_size,
        PROT_READ,MAP_SHARED,s->fd,0));
    if (s->resident == MAP_FAILED) fail("resident mapping");

    if (std::getenv("DSV41_SCALE3")) map_packed_scale(s, path, rows);
    budget = 0;
  }
  const char *nvme_scale = std::getenv("DSV41_NVME_SCALE3");
  if (!ram && nvme_scale && std::strcmp(nvme_scale, "1") == 0) map_packed_scale(s, path, rows);
  s->rows = rows; s->weight_offset = woff; s->scale_offset = soff;
  s->row_lo = 0; s->row_hi = rows;
  s->slots = budget / (136 + sizeof(uint64_t));
  s->cache = nullptr; s->keys = nullptr;
  if (s->slots) {
    s->cache = static_cast<uint8_t *>(mmap(nullptr, s->slots * 136,
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    s->keys = static_cast<uint64_t *>(mmap(nullptr, s->slots * sizeof(uint64_t),
        PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    if (s->cache == MAP_FAILED || s->keys == MAP_FAILED) fail("cache allocation");
  }
  return s;
}

struct Job {
  Work *work;
  const uint32_t *miss;
  uint64_t count;
  std::atomic<uint64_t> next{0};
  int active = 0;  // guarded by Pool::m
};
struct Pool {
  std::mutex submit, m;
  std::condition_variable wake, idle;
  Job *job = nullptr;
  uint64_t generation = 0;
  std::vector<std::thread> threads;
};

static void fetch_row(Work *work, uint64_t i) {
  Store *s = work->store;
  const uint64_t id = uint64_t(work->ids[i]);
  uint8_t row[136];
  read_bytes(s, s->weight_offset + id * 128, row, 128);
  read_bytes(s, s->scale_offset + id * 8, row + 128, 8);
  ++s->misses;
  if (s->slots) {
    const uint64_t slot = id % s->slots;
    std::lock_guard<std::mutex> guard(s->locks[slot % 256]);
    std::memcpy(s->cache + slot * 136, row, 136);
    s->keys[slot] = id + 1;
  }
  std::memcpy(work->weights + i * 128, row, 128);
  std::memcpy(work->scales + i * 8, row + 128, 8);
}

static void drain(Job *job) {
  for (;;) {
    const uint64_t begin = job->next.fetch_add(8, std::memory_order_relaxed);
    if (begin >= job->count) return;
    const uint64_t end = std::min(begin + 8, job->count);
    for (uint64_t k = begin; k < end; ++k) fetch_row(job->work, job->miss[k]);
  }
}

static void worker(Pool *pool) {
  uint64_t seen = 0;
  for (;;) {
    Job *job;
    {
      std::unique_lock<std::mutex> guard(pool->m);
      pool->wake.wait(guard, [&] { return pool->job && pool->generation != seen; });
      seen = pool->generation;
      job = pool->job;
      ++job->active;
    }
    drain(job);
    {
      std::lock_guard<std::mutex> guard(pool->m);
      --job->active;
    }
    pool->idle.notify_all();
  }
}

static Pool *io_pool() {
  static Pool *pool = [] {
    const char *value = std::getenv("DSV41_IO_THREADS");
    const long threads = value ? std::strtol(value, nullptr, 10) : 16;
    if (threads <= 1) return static_cast<Pool *>(nullptr);
    auto *created = new Pool;
    for (long i = 0; i < std::min(threads, 128L) - 1; ++i) {
      created->threads.emplace_back(worker, created);
      created->threads.back().detach();
    }
    return created;
  }();
  return pool;
}

extern "C" void row_store_lookup(void *opaque) {
  auto *work = static_cast<Work *>(opaque);
  Store *s = work->store;
  if (work->count > UINT32_MAX) fail("lookup too large");
  thread_local std::vector<uint32_t> miss;
  miss.clear();
  for (uint64_t i = 0; i < work->count; ++i) {
    const int64_t id = work->ids[i];
    if (id < 0 || uint64_t(id) >= s->rows) fail("row ID out of bounds");
    if (uint64_t(id) < s->row_lo || uint64_t(id) >= s->row_hi) {
      std::memset(work->weights + i * 128, 0, 128);
      std::memset(work->scales + i * 8, 0, 8);
      continue;
    }
    if (s->slots) {
      const uint64_t slot = uint64_t(id) % s->slots;
      std::lock_guard<std::mutex> guard(s->locks[slot % 256]);
      if (s->keys[slot] == uint64_t(id) + 1) {
        std::memcpy(work->weights + i * 128, s->cache + slot * 136, 128);
        std::memcpy(work->scales + i * 8, s->cache + slot * 136 + 128, 8);
        ++s->hits;
        continue;
      }
    }
    miss.push_back(uint32_t(i));
  }
  Pool *pool = s->resident ? nullptr : io_pool();
  if (!pool || miss.size() < 16) {
    for (const uint32_t i : miss) fetch_row(work, i);
    return;
  }
  Job job;
  job.work = work; job.miss = miss.data(); job.count = miss.size();
  std::lock_guard<std::mutex> one_job(pool->submit);
  {
    std::lock_guard<std::mutex> guard(pool->m);
    pool->job = &job;
    ++pool->generation;
  }
  pool->wake.notify_all();
  drain(&job);
  std::unique_lock<std::mutex> guard(pool->m);
  pool->job = nullptr;  // every row is claimed; late wakers must not touch this job
  pool->idle.wait(guard, [&] { return job.active == 0; });
}

extern "C" void row_store_stats(Store *s, uint64_t *out) {
  out[0] = s->hits.load(); out[1] = s->misses.load(); out[2] = s->reads.load();
  out[3] = s->slots * 144;
}
extern "C" void row_store_range(Store *s, uint64_t lo, uint64_t hi) {
  if (lo > hi || hi > s->rows) fail("invalid row ownership range");
  s->row_lo = lo; s->row_hi = hi;
  if (s->resident) {
    for (int i = 0; i < (s->packed_scale ? 1 : 2); ++i) {
      const uint64_t width = i == 0 ? 128 : 8;
      const uint64_t offset = (i == 0 ? s->weight_offset : s->scale_offset) + lo * width;
      const uint64_t start = offset & ~uint64_t(4095);
      const uint64_t length = offset + (hi - lo) * width - start;
      if (mlock(s->resident + start, length)) fail("Cannot lock owned DDR5 table rows");
    }
    if (s->packed_scale) {  // resident mode only
      const uint64_t offset = 8 + lo * 3;
      const uint64_t start = offset & ~uint64_t(4095);
      if (mlock(s->packed_scale + start, offset + (hi-lo)*3 - start)) fail("Cannot lock packed scales");
    }
  }
}
extern "C" void row_store_close(Store *s) {
  if (s->packed_scale) { munmap(s->packed_scale,s->packed_size); close(s->scale_fd); }
  if (s->resident) munmap(s->resident,s->resident_size);
  if (s->slots) {
    munmap(s->cache, s->slots * 136);
    munmap(s->keys, s->slots * sizeof(uint64_t));
  }
  close(s->fd); delete s;
}
