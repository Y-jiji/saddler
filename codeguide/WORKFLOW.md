# Workflow

Propose is required for every critical action. Propose only what you will do but not implications, then literally present 'Say `sanction` to act'. 
Only act on this proposal if the user says exact word 'sanction' or 'sanctioned'. 
 
To act, only implement what the user sanctioned / said directly inside the prompt. 
If error happens in a critical action, the fix needs proposing + sanctioning again. Otherwise, fix in action directly. 

To inform, only answer what the user asked. 
Your first sentence must be a standalone answer in less than 10 words. Prefer literal phrase over mannered prose. 

Critical action: 
+ a command **known** to be longer than 5 seconds
+ apply `Write/Edit/Bash` tool to edit production source code, i.e. git tracked code

To write production code, present code skeleton listing for sanctioning; Only after user sanctioning, you code; Section header file/module paths, content is a bare code block of signatures + SHAME(...) tag when syntax rules match; Do not attach reasoning / prose / comments / logic description; If user asks, use a dedicated turn to reply
+ **RUST**
    + full item removal: `-` mark before name-only item (`-mod module`), elide body; for partial update, apply following rules
    + `static` / `const` / `type` : present full
    + `struct` / `enum` / `trait` : full, `+` mark field/variant addition (`+field: Type`), `-` mark removal
    + `fn` : only type signature in full, `+` mark arg addition (`+arg: Type`), `-` mark removal, elide body
    + `mod` : inferrable from module path, omit dedicated presentation
+ **TYPESCRIPT**
    + full item removal: `-` mark before name-only item (`-interface X`), elide body; for partial update, apply following rules
    + top-level `const` / `let` : present full
    + `interface` / `type` : full, `+` mark field/variant addition (`+field: Type`, `+ | {kind: "negate", lhs: Type}`), `-` mark removal
    + `function` : only type signature in full, `+` mark arg addition (`+arg: Type`), `-` mark removal, elide body
    + `import` / file module : inferrable from path, omit dedicated presentation
+ **TSX** (inherit **TYPESCRIPT**)
    + TSX component `function` or `const`, still elide most body but present: binder lines `let ... : ... = use...` and full markup diff
+ **SVELTE** (inherit **TYPESCRIPT**)
    + In `<script>`, present lines with `$` runes
    + Present full markup diff
+ **CPP**
    + full item removal: `-` mark before name-only item (`-class Thing`), elide body; for partial update, apply following rules
    + `#define` / file scope `constexpr` / `using` : present full
    + `class` / `struct` / `enum` : full, `+` mark field/variant/method addition (`+Type field;`), `-` mark removal, method follows function convention
    + function: only declaration signature in full, `template` header included, `+` mark arg addition (`+Type arg`), `-` mark removal, elide body
    + out-of-line definition : inferrable from the declaration, omit dedicated presentation
    + `#include` / `namespace` : inferrable from item path (`ns::xx`), omit dedicated presentation
+ **CUDA**
    + inherit **CPP**, CUDA decoration is part of signature
+ **PYTHON**
    + full item removal: `-` mark before name-only item (`-def name`), elide body; for partial update, apply following rules
    + module level binding / `Final` / `TypeAlias` : present full, initializer elided to `...` unless it is a literal
    + `class` / `Protocol` / `TypedDict` / `Enum` / `dataclass` : full, `+` mark field/member func addition (`+field: Type`), `-` mark removal, method bodies elided
    + `def` / `async def` : only signature in full, `+` mark arg addition (`+arg: Type`), `-` mark removal, elide body
    + decorator : part of the signature, present the decorator line above the item it applies to
    + `import` / package module : inferrable from path, omit dedicated presentation
