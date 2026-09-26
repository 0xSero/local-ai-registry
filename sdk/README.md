# sdk

Two tiny clients for the registry, one file each, no dependencies. Both fetch `https://local.sybilsolutions.ai/api/v2/catalog.json`, find the card a GPU name belongs to, and print the steps that run its recipe.

**JavaScript** (`sdk/js`, Node 18+, Deno, Bun, browsers; the website uses it too):

```js
import { pick, command } from "@sybilsolutions/local-ai";
const r = await pick({ gpu: "NVIDIA GeForce RTX 4090", vram: 24 });   // or { all: true } for the top three
console.log(command(r));
```

**Python** (`sdk/python`, 3.9+, standard library):

```python
from local_ai_registry import pick, command
print(command(pick("NVIDIA GeForce RTX 4090", vram=24)))
```

or straight from a shell: `python3 sdk/python/local_ai_registry.py "RTX 4090" 24`.

| Function | Returns |
|---|---|
| `catalog()` | The whole catalog: cards with their picks, recipes with rendered launches, models |
| `detect(catalog, gpu, vram)` | The card id for a GPU name as nvidia-smi, amd-smi or lspci prints it |
| `pick(gpu, vram, all)` | The recommended recipe, or the card's top three |
| `steps(recipe)` | Download the weights, write the config, start the container: title and code each |
| `command(recipe)` | The same steps as one shell script |
