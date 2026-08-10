# Coding

To write code, present code skeleton listing for sanctioning; Only after user sanctioning, you code; Use nested bullet list, 1st level file paths, 2st level signatures; Do not attach reasoning / prose / comments / logic description; If user asks, use a dedicated turn to reply
<<RUST>>
+ for full removal, present full item (remove `static VAR`, `const VAR`)
+ `static` / `const` / `type` : present code block in full
+ `struct` / `enum` / `trait` : present code block in full, if addition only, elide unchanged parts
+ `fn` : elide function body, present function signature in full
+ `mod` : inferrable from path, omit dedicated presentation
<<TYPESCRIPT>>
+ for full removal, present full item (remove `const VAR`, `type T`)
+ module level `const` / `let` / `type` : elide body, present type signatures in full
+ `interface` : present code block in full, if addition only, elide unchanged parts
+ `function` : elide function body, present function signature in full
+ `import` / file module : inferrable from path, omit dedicated presentation
<<TSX>>
+ inherit `<<TYPESCRIPT>>`
+ component `function` : elide body except state, present component signature in full
+ state : present every `useState` / `useReducer` / `useRef` / `useContext` / `useMemo` binding by signature, one per line, declaration order, type argument in full, initializer elided to `(...)` unless it is a literal
+ effect / handler / callback : elide body, present name and signature only
+ JSX : omit unless the element tree itself changes, then present tag skeleton only, no props, no text
<<CPP>>
+ for full removal, present full item (remove `#define VAR`, `constexpr VAR`)
+ `#define` / file scope `constexpr` / `using` : present code block in full
+ method / free function : elide body, present declaration signature in full, `template` header included
+ out-of-line `inline` definition : inferrable from the declaration, omit dedicated presentation
+ `#include` / `namespace` : inferrable from item path (`ns::xx`), omit dedicated presentation 
<<CUDA>>
+ inherit `<<CPP>>`, CUDA decoration is part of signature

To write a syntax item, use the following convention:
<<RUST>>
+ `static` / `const` name : one word or two word `SNAKE_CAPITAL_CASE`
+ `struct` / `enum` / `trait` / `type` name : normal `CamelCase`
    + `struct` field name : one word, or two word `flatcase`, per struct fields all same length
    + `enum` variant name : one word, or two word `CamelCase`, per enum variants all same length
+ `fn` / `let` / `mod` name : one word, or two word `flatcase`
+ `comment` : always use `/// `, do not comment in function bodies; per block at most 60 words.
+ `comment` : add literal tags in comments to functions more than 60 lines `SHAME(TALLFUNC)` / 120 chars `SHAME(WIDEFUNC)` / 6 args `SHAME(MANYARG)`
<<TYPESCRIPT>>
+ `const` name : literal constant one word or two word `SNAKE_CAPITAL_CASE`, otherwise one word or two word `camelCase`
+ `interface` / `type` name : normal `CamelCase`
    + field name : one word, or two word `camelCase`
    + string union member : one word `lowercase`, per union members all same length
+ `function` / `let` name : one word, or two word `camelCase`, file name `kebab-case`
+ this-less object : no `class` / `this` / `new`; a type is an `interface` of `readonly` fields plus method signatures, and a `xOf(...)` constructor binds free module level `function name(x: X, ...args)` onto a plain object literal and returns it
+ this-less transition : never mutate, rebuild through the constructor and return a fresh object, or the input untouched when nothing changed; invariants live in normalizers the constructor composes
+ `comment` : always use `/** */` above the item, do not comment in function bodies; per block at most 60 words
+ `comment` : add literal tags in comments to functions more than 60 lines `SHAME(TALLFUNC)` / 120 chars `SHAME(WIDEFUNC)` / 6 args `SHAME(MANYARG)`
<<TSX>>
+ inherit `<<TYPESCRIPT>>`
+ component name : normal `CamelCase`, file name is its `kebab-case`
+ props type name : `<Component>Props`, destructured in the signature, never read through one `props` binding
+ hook name : `use` prefix then one word, or two word `camelCase`
+ state binding : `const [thing, setThing] = useState<T>(...)`, setter is the field name under a `set` prefix
+ handler name : `on<Event>` as a prop, `handle<Event>` in the body
+ function components only, no module level mutable; domain logic lives in a this-less object in a `.ts` module the component holds in state
<<CPP>>
+ `#define` / file scope `constexpr` / block scope compile time `constexpr` name : one word or two word `SNAKE_CAPITAL_CASE`, a macro carries its component as prefix
+ `class` / `struct` / `enum` name : normal `CamelCase`, a hardware prefix stays an acronym
    + field name : one word, or two word `flatcase`, same `struct` / `class` field names should have all same length
    + `enum` variant name : one word, or two word `SNAKE_CASE`, per enum variants all same length
+ no nested function body inside `class`
+ method / free function / local name : one word, or two word `flatcase`; a file scope free function is `static`
+ `template` parameter name : one word `SNAKE_CAPITAL_CASE`, a `bool` predicate parameter one word `flatcase`
+ `comment` : always use `/** @brief */` on the declaration, one line each for `@tparam` / `@param` / `@return`; in function bodies only numbered step markers `// [1]`; per block at most 60 words
+ `comment` : add literal tags in comments to functions more than 60 lines `SHAME(TALLFUNC)` / 100 chars `SHAME(WIDEFUNC)` / 6 args `SHAME(MANYARG)`
<<CUDA>>
+ inherit `<<CPP>>`
+ `comment` : a kernel documents its index layout, not its arithmetic; the buffer order it maintains belongs in the `@class` block

To write a test, following listed convention; test is code, so it requires the same present + sanction process:
<<RUST>>
+ all `#[test]` lives in `mod correct` (correctness testing) or `mod profile` (performance testing)
+ for shared but test-only tools for multiple modules, implement `mod fixture`
+ for each test, target a general property. tests should systematically eliminate classes of bugs, so we prefer fuzzing. when implementation is wrong in any sense, at least one test fails with probability > 0
<<TYPESCRIPT>>
+ all tests live in `<item>.test.ts` beside the item
+ for each test, target a general property. tests should systematically eliminate classes of bugs, so we prefer fuzzing. when implementation is wrong in any sense, at least one test fails with probability > 0
+ for a this-less object, fuzz a random transition sequence and assert every invariant holds on the returned object and no input object was mutated
<<TSX>>
+ inherit `<<TYPESCRIPT>>`
+ test state, not markup : drive the component through its state signatures, assert on rendered role / text, never on class name or element tree
+ a component test never covers domain logic; that property belongs to the `.ts` module's own test
<<CPP>>
+ all tests live in `unittest/`, one file one `main` returning 0 on pass and 1 on fail, named `test_<unit>_<property>` (correctness testing) or `prof_<unit>` (performance testing), registered in `CMakeLists.txt` by `add_executable` then `add_test` under the same name
+ a test is a `bool run_<property>(args, seed)` over `std::mt19937 rng(seed)` inputs; `main` drives a table of `{name, fn, args}` rows and prints `[PASS] name` / `[FAIL] name` per row
+ for each test, target a general property. tests should systematically eliminate classes of bugs, so we prefer fuzzing. when implementation is wrong in any sense, at least one test fails with probability > 0. more over, profile tests output performance stats for the target function. 
<<CUDA>>
+ inherit `<<CPP>>`
+ one table row per template instantiation, sweeping the whole parameter space the unit claims to support, seed varying per row
+ the unit test is driven on the smallest launch shape exhibiting the property; assert on host after `cudaDeviceSynchronize` and copy back, never inside a kernel

# Surveying

To survey a paper/chapter, report exactly 5 sentences (each sentence at most 400 chars):
+ **Problem** What final problem/motivation is the paper addressing? Maybe this paper is targeting a subproblem, report both the major problem which role the subproblem plays. 
+ **Insight** What did the author see from the problem? There must be a correct intuition that directly drives the method. Given the insight, a near-domain expert with sufficient background should be able to derive the method without external help. 
+ **Method** What path did this paper take to solve the problem? What are the technical details that the insight did not cover?
+ **Result** To what extent is the problem solved? Metrics? Empirical Observation?
+ **Impact** So what? Why do people care?

If the paper describes a long-running, multi-stage effort; Report the full lineage of efforts in temporal order; Each effort maps to the 5-sentence format. 

# Writing

To fill in the 5 elements, there are several strategies: 
+ **Problem** 
+ **Insight** 
+ **Method** 
+ **Result** 
+ **Impact** 

# Versioning

Commit message: `feature/refactor/chore/test/fix`, top-level crate/module/file path in parentheses, e.g. `feature(some_crate): ...`, only one line
Just push: code only goes into git push, never copy code files directly unless you are sure that the script can only ever exists on the server and never enter github
Commit as you go: when building a large set of features, commit changes as you go
No worktree: do not create worktrees, user don't ask for overlapping changes
