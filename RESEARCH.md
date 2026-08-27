Locate the artifact of this paper:
+ If the repository is not given in context, ask the user for its location. 
+ If different configurations / components drastically shifts the functionality / characteristics of the system, ask user which. 
+ Insert into CLAUDE.md; The location and chosen configurations / components only, typically under 200 words. 

To write a section, present section skeleton listing for sanctioning; Only after user sanctioning, you write; 
Use nested bullet list, subsection header as level 1, paragraph siganture as level 2; 
Do not attach reasoning / prose / comments / logic description; If user asks, use a dedicated turn to reply; 
<<PARAGRAPH SIGNATURE>>
+ one line summary of paragraph
+ code source that you will fully transcribe into natural language text but not refer to (file name + syntax items only)
+ citations (paper name / title only)
+ artifacts: figure (file name only), pseudo code (algorithm name only)

To draw a figure, present plot skeleton for sanctioning; Only after user sanctioning, you plot. 
Use nested bullet list, subplot topic + estimated blank rate as level 1 (`survivor change with iterations, blank rate 0.5`), element inside subplot as level 2 (`scatter #ff0000 marker 'x' s=20 x="number of iterations" y="distance of expanded node"`, `axis x:100~200 y:200~248.5 (legend ...)`)
Do not attach reasoning / prose / comments / logic description; If user asks, use a dedicated turn to reply; 
+ Use a prefix of (Red #ff0000, Blue #0000ff, Green #00ff00, Cyan #00ffff, Magenta #ff00ff, Orange #ff8100)
    + Antithesis: (Red, Green) skips Blue, so it is not a prefix
+ Font size should be exactly the same as caption size AFTER PLACEMENT INSIDE THE PAPER; Do your math to get proper font size. 
+ Report estimated blank rate := a maximum area of a rectangle with one-side on plot boundary & intersecting no element / total plot area. 
+ Prefer `uv` to manage dependencies; save figure as `fig_<...>.svg`

To survey a paper/chapter/blog, always download the original source `<FILE>.pdf` into dedicated folder, then write exactly 5 sentences (each sentence at most 400 chars) into `<FILE>.md`:
+ **Problem** What final problem/motivation is the paper addressing? Maybe this paper is targeting a subproblem, report both the major problem which role the subproblem plays. 
+ **Insight** What did the author see from the problem? There must be a correct intuition that directly drives the method. Given the insight, a near-domain expert with sufficient background should be able to derive the method without external help. 
+ **Method** What path did this paper take to solve the problem? What are the technical details that the insight did not cover?
+ **Result** To what extent is the problem solved? Metrics? Empirical Observation?
+ **Impact** So what? Why do people care?

If the paper describes a long-running, multi-stage effort or build on the top of prior work. 
Trace the full lineage of efforts in temporal order, download and survey these papers recursively like before, but one at a time. 
