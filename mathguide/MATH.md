Propose is required for every critical action. Propose only what you will do but not implications, then literally present 'Say `sanction` to act'. 
Only act on this proposal if the user says exact word 'sanction' or 'sanctioned'. 
 
To act, only implement what the user sanctioned / said directly inside the prompt. 
If error happens in a critical action, the fix needs proposing + sanctioning again. Otherwise, fix in action directly. 

To inform, only answer what the user asked. 
Your first sentence must be a standalone answer in less than 10 words. Prefer literal phrase over mannered prose. 

Critical action: 
+ a command **known** to be longer than 5 seconds
+ apply `Write/Edit` tool to edit production source code, i.e. git tracked code (don't apply `Bash`)

To write Lean, present code skeleton listing for sanctioning; Only after user sanctioning, you write; Use nested bullet list, 1st level file paths, 2st level signatures; Do not attach reasoning / prose / comments / proof sketch; If user asks, use a dedicated turn to reply
+ for full removal, present full item (remove `def name`, `abbrev name`)
+ `structure` / `inductive` / `class` : present code block in full, if addition only, elide unchanged parts
+ `abbrev` (type alias) : present code block in full
+ `def` / `theorem` / `lemma` / `instance` : elide body, present signature in full (implicit args, type class constraints, return type)
+ `namespace` / `section` / `import` / `open` : inferrable from path, omit dedicated presentation

To write a syntax item, use the following convention:
+ `structure` / `inductive` / `class` name : normal `CamelCase`
    + field name : one word, or two word `camelCase`
    + constructor name : one word, or two word `camelCase`
+ `def ... : Type` : normal `CamelCase`
+ `namespace` / file : `CamelCase`
+ normal `def` / `theorem` / `lemma` / `instance` name : one word, or two word `camelCase`
+ `universe` variable : Unicode or Greek letter
+ `comment` : always use `/-- -/` above the item, `--` inline; per block at most 60 words
+ `comment` : add literal tags in comments to functions more than 60 lines `SHAME(TALLFUNC)` / 120 chars `SHAME(WIDEFUNC)` / 6 args `SHAME(MANYARG)`

To check a property, following listed convention; the type check is the proof, so there is no randomized test requirement:
+ exploration and property checks live in `<File>Scratch.lean` beside `<File>.lean`
+ `example` for anonymous property checks only, lives in the scratch file
+ `#eval` / `#check` / `#reduce` for throwaway exploration, lives in the scratch file, never committed
