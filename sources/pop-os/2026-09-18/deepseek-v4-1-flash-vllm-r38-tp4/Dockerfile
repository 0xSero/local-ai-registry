# Local Inference Lab jovian-judgement r38, unchanged; only the entrypoint is switched to the image's own
# DeepSeek-V4.1 launcher because the Local Studio controller cannot override entrypoints.
FROM localinferencelab/vllm@sha256:f41ca8bb10bb3a125a50340d70d39ad4b7f5605f3fcb661bc992ed0bc4701a00
ENTRYPOINT ["/usr/local/bin/serve-ds41-jovian.sh"]
