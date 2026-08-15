# Writing (Computing Systems Paper)

Given the target venue, you can scaffold the project: 
+ `template/` for venue template files
+ `survey/` for survey dump and insight markdown
+ `build/` for all build output (git ignore)
+ `main.tex` for compile entry point
+ `section_<...>.tex` for section
+ `.latexmkrc` for compile information
+ `.nvim.lua` for lsp setup, read `~/.config/nvim/init.lua` for convention

Locate the artifact of this paper:
+ If the repository is not given in context, ask the user for its location. 
+ If different configurations / components drastically shifts the functionality / characteristics of the system, ask user which. 
+ Insert into CLAUDE.md; The location and chosen configurations / components only, typically under 200 words. 

To write a section, present section skeleton listing for sanctioning; Only after user sanctioning, you write; Use nested bullet list, section header as inner node, paragraph siganture as leaf; Do not attach reasoning / prose / comments / logic description; If user asks, use a dedicated turn to reply; For unknown, leave `\todo`.  
<<PARAGRAPH SIGNATURE>>
+ one line summary of paragraph
+ code source that you will fully transcribe into natural language text but not refer to (file name + syntax iitems only)
+ citations (paper name / title only)
+ artifacts: figure (name only), pseudo code (algorithm name only)

To draw a figure:
+ Figure should use (Black #000000, Red #ff0000, Blue #0000ff, Green #00ff00, Cyan #00ffff, Magenta #ff00ff, Orange #ff8100)
+ Each figure group use a prefix of these colors: e.g. (Black, Red, Blue); Skipping is violation: (Black, Red, Green)
+ Prefer concrete color over transparent
+ Prefer matplotlib `fig_<...>.svg` from `fig_<...>.py`

# Surveying

To survey a paper/chapter/blog, always download the original source `<FILE>.pdf` into dedicated folder, then write exactly 5 sentences (each sentence at most 400 chars) into `<FILE>.md`:
+ **Problem** What final problem/motivation is the paper addressing? Maybe this paper is targeting a subproblem, report both the major problem which role the subproblem plays. 
+ **Insight** What did the author see from the problem? There must be a correct intuition that directly drives the method. Given the insight, a near-domain expert with sufficient background should be able to derive the method without external help. 
+ **Method** What path did this paper take to solve the problem? What are the technical details that the insight did not cover?
+ **Result** To what extent is the problem solved? Metrics? Empirical Observation?
+ **Impact** So what? Why do people care?

If the paper describes a long-running, multi-stage effort or build on the top of prior work. 
Trace the full lineage of efforts in temporal order, download and survey these papers recursively like before, but one at a time. 
