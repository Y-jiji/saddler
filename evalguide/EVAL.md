Please work interactively with user, or work autonomously if and only if you are given explicitly granted time and budget.

In interactive mode, before launch experiments, always answer the following and confirm with users: 
- What is the expected resource consumption? Report in dollars / credits / SUs. 
- What do you expect to see? How will result look like? Report in metrics numbers. 
- When will the user see preliminary results? If it comes in, report to user immediately as simple scalar numbers. 
- When will the user see full results as plots?

When user grant you time and budget, you should propose to enter autonomous mode.
To enter autonomous mode, present the following and wait for user confirmation (exact word `sanction` from user):
- How many iterations can you do before consuming all the time and budget? Provide an one sentence answer. 
- How can user know your progress per iteration? Provide a one-paragraph answer in 200 words. 
- What will be the deliverable standard? If already given by user, just parapharse in your words but specify verifiable metrics. Provide a one-paragraph answer within 200 words. Shorter is better.
- How many iterations can you do before consuming all the time and budget? Is that enough? Provide an one sentence answer.
- Check list about iterations: 
    - One iteration (i) := 
        1. taking feedback from evaluation/profile results from last iteration i-1 (for first iteration, take feedback from prior results)
        2. adjust to make improvement. set expectations about current improvement(i). 
        3. a launch with current improvement(i). 
    - A batched/queued launch count as ONLY ONE iteration(i) because it does not carry multiple improvements (i,i+1,...). 
    - A useful strategy to increase the number of iterations is to interpolate/scale-down the evaluation -- setting up a proxy goal.  
        - If you set a proxy goal for the iteration, do you expect it to extrapolate/scale-up to real goal? 
        - Actively find negative empirical evidence against extrapolation. If you find such negative evidence, adjust the proxy goal. 

At the start of autonomous mode, set up a 15 minute periodic poll that only tells you 15 minutes passed to help you keep track of time.

In autonomous mode, you can work iteratively to reach the goal set by user.

In each iteration:
- How many iterations are left before consuming all the time and budget? Can you reach the goal in that many iterations?
- What will result of current launch look like? How does this result help you reach the goal? What is the next step?

Inside `\d{4}/README.md` -- e.g. `0000/README.md`

- Template for goal (only written by user, not you):
    If it is not already in the file, provide a link to open such `README.md`
    ```markdown
    # Goal
    ...
    ```

- Template for metrics (column names inside CSVs):
    ```markdown
    # Metrics
    - `[METRIC NAME]`: ...
    - `[METRIC NAME]`: ...
    - `[METRIC NAME]`: ...
    ```
    `[METRIC NAME]` must be exactly the same vocabulary used inside `Run` and `Analysis` section. 
    The description part should contain 'written as ...', which is exactly the same vocabulary used inside `Figure` section. 

- Template for figure section:
    ```markdown
    # Figure
    `uv run [SCRIPT].py [INPUT FILE NAMES] [NAME].svg`
    ![]([NAME].svg)
    ```
    - `[SCRIPT]`: plotting script, must run in current directory on current machine
    - `[INPUT FILE NAMES]`: must be in current directory, produced by analysis script
    - `[NAME].svg`: the output file name

- Template for documenting benchmark runs:
    ```markdown
    # Run

    | ID | COMMAND | VERSION | STATE | WHERE | OUTPUT |
    | --- | --- | --- | --- | --- | --- |
    | [ID] | [BINDARY NAME] [PARAMETERS] | [GIT REPO]\@[COMMIT HASH] | [STATE OF CURRENT COMMAND] | [SERVER NAME] | [OUTPUT FILE NAMES] |
    ```
    `[ID]`: a short id you give to this row, no duplication (globally)
    `[BINARY NAME] [PARAMETERS]`:
    - must be a binary that runs the workload
    - parameters are parameters, not compound commands
    - additional environment vars prefix are allowed (ONLY HERE)
    - we explicitly forbid one script that does a lot of things
    `[GIT REPO]\@[COMMIT HASH]`: commit hash of the repository that produced the binary
    `[STATE OF CURRENT COMMAND]`:
    - `Queued(AFTER ...; EST [START]~[END])`: first ... is a row `[ID]`; `[START]` and `[END]` are two ISO-8601 standard timestamps.
    - `Running(EST [START]~[END])`: `[START]` and `[END]` are ISO-8601 standard timestamps.
    - `Finished([END])`: `[END]` is an ISO-8601 standard timestamp.
    `[SERVER NAME]`:
    - ssh login host name or computational resource name (gcloud)
    `[OUTPUT FILE NAMES]`
    - a list of `[FILE NAME]`, each `[FILE NAME]` is an absolute path, if inside current user home, `~` abbreviation is allowed.
    - prefixes like `ftp` and `gcloud` are allowed.

- Template for documenting benchmark runs:
    ```markdown
    # Analyze

    | ID | SCRIPT | INPUT | OUTPUT |
    | [ID] | [SCRIPT] | [INPUT FILE NAMES] | [OUTPUT FILE NAMES] |
    ```
    `[ID]`: short id you give to this row, no duplication (globally)
    `[SCRIPT]`: analysis script
    - It must be inside current numbered directory
    - It must be a linear script:
        - for python, no function
        - for rust, everything in `fn main` function body
    - It must run with one of the following:
        - `uv run --script [SCRIPT] [INPUT FILE NAMES] [OUTPUT FILE NAMES]`
        - `cargo +nightly -Zscript [SCRIPT] [INPUT FILE NAMES] [OUTPUT FILE NAMES]`
    `[INPUT FILE NAMES]`: files generated by runs
    - Files generated one `Running/Finished` runs
    - Exactly the same as one of the `[OUTPUT FILE NAMES]` of that `Running/Finished` row
    `[OUTPUT FILE NAMES]`: output files generated by output script
    - Generated file must be copied into current numbered directory aside current `README.md`
    - Prefer csv files
    - A single analysis output must be under 5M (sum of all output files produced by one analysis script execution)

- Template for change log:
    ```markdown
    # Change Log
    - [ONE LINE MESSAGE ABOUT THE CHANGE]
    - [ONE LINE MESSAGE ABOUT THE CHANGE]
    - [ONE LINE MESSAGE ABOUT THE CHANGE]
    ```
