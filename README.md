# local-ai-registry

Registry of hardware, models, recipes, model instances, and prices for local AI.

## Structure

```
local-ai/
hardware/         — GPU and accelerator profiles (VRAM, bandwidth, topology)
models/            — model metadata (family, parameters, context, quantizations)
recipes/           — launch recipes (engine, engine config, GPU topology, performance)
model-instances/   — concrete model-on-hardware instances (measured runs)
prices/            — hardware price snapshots by region (US, GB, DE, JP, PL)
```

## License

MIT
