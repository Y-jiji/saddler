---
name: optimize
description: optimize a target in model-experiment iterations until the given time budget runs out
disable-model-invocation: true
---

Optimize the target iteratively. Wake yourself up at least once every 15 minutes. Do the following per iteration. 
1. Model: explain the mechanism for creating the alpha. model PnL (profit and loss): 
    - Alpha: profitable directions
    - Overhead: extra cost added, how large are they
    - Risk: exposure to unwanted factors
2. Backtest: verify your observations. make sure the objective moves as expected when you move that factor alone.
    - Scale-down: you can set a scale-down experiment (smaller scale, less datasets, ...) to cut wrong observation early
    - Oracle: fix other factors using oracle / trace info (whenever possible) to separate the factor
    - Can you verify each assumption in 1 minute? If not, reflect. You are obligated to make it quick
3. Build: combine observations into an executable algorithm. add needed profile counters
4. Execute: run the algorithm end-to-end
5. Attribution: attribute PnL to changed components. check if the split is expected
