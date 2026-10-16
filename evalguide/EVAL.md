A research / evaluation folder should be organized in the following way: 
- evaluated repos are submodules `./<SUBMODULE>`
- everything else should be organized like `./#001/`, `./#002`, ...; 
  Take `#001` as example. It should contain the following sections. 
  - Research Question: question/context written by human
  - Metrics: each addition / reduction must be thoroughly discussed with human, a bullet list of `<TERM>: <DEFINITION>`
  - Run: content is a table only 
    `Command` is the exact command being run. 
    `Hash` is the commit hash of the current repo when the script is run. 
    `Status` describes how the run goes, including which machine, etc. 
    `Output` are the output files, which server, and its path. 
    ```markdown
    | Command | Hash | Status | Output |
    | ---     | ---  | ---    | --     |
    | ...     | ...  | ...    | ...    |
    ```
  - Analyze: content is a table only
    `Script` should be a simple bash / python script that only takes a list of file names as content, and be a PURE FUNCTION of these file contents. Script file name only. 
    `Input` input file names.
    `Output` is the output file name (base + ext only); The script typically runs on a server elsewhere, but you must copy the output into current `#001` folder; Output file of an analyze script should be small, 1MB maximum. 
    ```markdown
    | Script  | Input | Output |
    | ---     | ---   | ---    |
    | ...     | ...   | ...    |
    ```
  - Figures: (one command + one image) * n
    The command prefix only takes file names as arguments and must be a PURE FUNCTION of these files.  
    All inputs must be available as some `./#001/<FILE NAME>`, and 1MB maximum. 
    ```markdown
    `uv run some_figure.py <INPUT1> <INPUT2> ...`
    ![#](some_figure.svg)
    ```
