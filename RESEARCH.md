# Surveying

To survey a paper/chapter/blog, always download the original source `<FILE>.pdf` into dedicated folder, then write exactly 5 sentences (each sentence at most 400 chars) into `<FILE>.md`:
+ **Problem** What final problem/motivation is the paper addressing? Maybe this paper is targeting a subproblem, report both the major problem which role the subproblem plays. 
+ **Insight** What did the author see from the problem? There must be a correct intuition that directly drives the method. Given the insight, a near-domain expert with sufficient background should be able to derive the method without external help. 
+ **Method** What path did this paper take to solve the problem? What are the technical details that the insight did not cover?
+ **Result** To what extent is the problem solved? Metrics? Empirical Observation?
+ **Impact** So what? Why do people care?

If the paper describes a long-running, multi-stage effort or build on the top of prior work. 
Trace the full lineage of efforts in temporal order, download and survey these papers recursively like before, but one at a time. 

# Writing (Computing Systems Paper)

Given the target venue, you can scaffold the project with (`main.tex`, `section_<...>.tex` regardless of the content). 

A typical computing systems paper contains: 
+ **Introduction** What attracts domain-experts / engineers to read / follow this work?
+ **Background + Related Work** What observation/oppotunity in **prior systems/techniques/applications** motivates current approach? What systems are functionally the same as ours?
+ **Method** Given the observations listed in background, how do we use the observation to build a better system?
+ **Implementation** What is **not** driven by background but implements differently from the baseline / specificly chosen in the code architecture so that it does not affect the main thesis but still affects evaluation in a profound way?
+ **Evaluation** How do we compare current system to other solutions? Metrics? Empirical Observations?

Locate the artifact of this paper:
+ If the repository is not given in context, ask the user for its location. 
+ If different configurations / components drastically shifts the functionality / characteristics of the system, ask user which. 
+ **ARTIFACT.md** should be generated, describe the location and chosen configurations / components only, typically under 200 words. 

To generate references for this paper: 
+ **references.bib** containing the bibtex related to given code repository (if not given, ask), sorted by years until now (use `date` command)
+ **survey** each paper's original file and 5-sentence markdown into `survey/` folder

To design an end2end experiment for this paper, present code skeleton listing for sanctioning; Only after sanctioning, you expand the skeleton to a subsection under evaluation; Do not attach reasoning / prose / comments / logic description; If user asks, use a dedicated turn to reply: 
+ **Platform** where/how will you run the code? (special cpu feature / memory spec / other device used)
+ **Workload** what workload will you run for each system? (short, 60 words max)
+ **Systems** what system will you run for the given workload? (just list + configuration)
+ **Metrics** what performance characteristics will you collect for each run? (each metrics definition)
+ **Figures** how do you present these in the paper? (each figure group, file names + short caption (40 words max) + color assignment only)

To draw a figure:
+ Figure should use (Black #000000, Red #ff0000, Blue #0000ff, Green #00ff00, Cyan #00ffff, Magenta #ff00ff, Orange #ff8100)
+ Each figure group use a prefix of these colors: e.g. (Black, Red, Blue); Skipping is violation: (Black, Red, Green)
+ Prefer concrete over transparent
+ Prefer matplotlib `fig_<...>.svg` from `fig_<...>.py`
