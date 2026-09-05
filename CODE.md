To write code, present code skeleton listing for sanctioning; Only after user sanctioning, you code; Use nested bullet list, 1st level file paths, 2st level signatures + SHAME(...) tag when syntax rules match; Do not attach reasoning / prose / comments / logic description; If user asks, use a dedicated turn to reply
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
<<SVELTE>>
+ inherit `<<TYPESCRIPT>>`
+ component `.svelte` file : elide `<script>` body except state, present the `$props()` destructuring in full
+ state : present every `$state` / `$state.raw` / `$derived` / `$derived.by` / `$props` / `$bindable` / `getContext` binding by signature, one per line, declaration order, type argument in full, initializer elided to `(...)` unless it is a literal
+ `$effect` / handler / callback : elide body, present name and signature only
+ markup : omit unless the element tree itself changes, then present tag skeleton only, no attributes, no text; `{#if}` / `{#each}` / `{#await}` / `{#key}` / `{#snippet}` count as tags
+ `<style>` : omit dedicated presentation
<<CPP>>
+ for full removal, present full item (remove `#define VAR`, `constexpr VAR`)
+ `#define` / file scope `constexpr` / `using` : present code block in full
+ method / free function : elide body, present declaration signature in full, `template` header included
+ out-of-line `inline` definition : inferrable from the declaration, omit dedicated presentation
+ `#include` / `namespace` : inferrable from item path (`ns::xx`), omit dedicated presentation 
<<CUDA>>
+ inherit `<<CPP>>`, CUDA decoration is part of signature
<<PYTHON>>
+ for full removal, present full item (remove `def name`, `VAR: Final = ...`)
+ module level binding / `Final` / `TypeAlias` : present code block in full, initializer elided to `...` unless it is a literal
+ `class` / `Protocol` / `TypedDict` / `Enum` / `dataclass` : present code block in full, field annotations included, method bodies elided; if addition only, elide unchanged parts
+ `def` / `async def` : elide function body, present signature in full, annotations and return type included
+ decorator : part of the signature, present the decorator line above the item it applies to
+ `import` / package module : inferrable from path, omit dedicated presentation

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
+ `export const` / `export interface` / `export function` : use `export` on items directly
+ a top-level item must be recursively constant, not only itself is a constant, anything it references / accessible through a pointer must be a constant. 
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
<<SVELTE>>
+ inherit `<<TYPESCRIPT>>`
+ component name : normal `CamelCase`, file name is that name plus `.svelte`; a plain module file stays `kebab-case.ts`
+ props type name : `<Component>Props`, destructured in `let { ... }: <Component>Props = $props()`, never read through one `props` binding
+ rune module name : shared reactive state lives in `<thing>.svelte.ts`, exported factory one word, or two word `camelCase`
+ state binding : `let thing = $state<T>(...)` written through direct assignment, no setter pair; a computed one is `const thing = $derived(...)`
+ handler name : `on<Event>` as a prop, `handle<Event>` in the body
+ one component per file, no module level mutable in `<script module>`; domain logic lives in a this-less object in a `.ts` module the component holds in `$state`
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
<<PYTHON>>
+ module level constant name : one word or two word `SNAKE_CAPITAL_CASE`, annotated `Final`
+ `class` / `Protocol` / `TypedDict` / `Enum` name : normal `CamelCase`
    + field name : one word, or two word `snake_case`, per class fields all same length
    + `Enum` member name : one word, or two word `SNAKE_CAPITAL_CASE`, per enum members all same length
+ `def` / local / parameter name : one word, or two word `snake_case`, file name `snake_case`
+ every parameter and return annotated, no bare `Any`; no module level mutable
+ `comment` : always use `"""..."""` as the first statement of the item, do not comment in function bodies; per block at most 60 words
+ `comment` : add literal tags in comments to functions more than 60 lines `SHAME(TALLFUNC)` / 120 chars `SHAME(WIDEFUNC)` / 6 args `SHAME(MANYARG)`

To write a test, following listed convention; test is code, so it requires the same present + sanction process:
<<RUST>>
+ all `#[test]` lives in `mod correct` (correctness testing) or `mod profile` (performance testing)
+ `#[test]` functions do not have to follow the naming convention for the production part
+ for shared but test-only tools for multiple modules, implement `mod fixture` parallel to `mod correct` and `mod profile`
+ for each test, target a general property. tests should systematically eliminate classes of bugs, so we prefer fuzzing. when implementation is wrong in any sense, at least one test fails with probability > 0
<<TYPESCRIPT>>
+ all tests live in `<item>.test.ts` beside the item
+ for each test, target a general property. tests should systematically eliminate classes of bugs, so we prefer fuzzing. when implementation is wrong in any sense, at least one test fails with probability > 0
+ for a this-less object, fuzz a random transition sequence and assert every invariant holds on the returned object and no input object was mutated
<<TSX>>
+ inherit `<<TYPESCRIPT>>`
+ test state, not markup : drive the component through its state signatures, assert on rendered role / text, never on class name or element tree
+ a component test never covers domain logic; that property belongs to the `.ts` module's own test
<<SVELTE>>
+ inherit `<<TYPESCRIPT>>`
+ a component test lives in `<Component>.svelte.test.ts` beside it, a rune module test in `<thing>.svelte.test.ts`, both compiled so runes are live
+ test state, not markup : drive the component through its props and state signatures, assert on rendered role / text, never on class name or element tree
+ a component test never covers domain logic; that property belongs to the `.ts` module's own test
<<CPP>>
+ all tests live in `unittest/`, one file one `main` returning 0 on pass and 1 on fail, named `test_<unit>_<property>` (correctness testing) or `prof_<unit>` (performance testing), registered in `CMakeLists.txt` by `add_executable` then `add_test` under the same name
+ a test is a `bool run_<property>(args, seed)` over `std::mt19937 rng(seed)` inputs; `main` drives a table of `{name, fn, args}` rows and prints `[PASS] name` / `[FAIL] name` per row
+ for each test, target a general property. tests should systematically eliminate classes of bugs, so we prefer fuzzing. when implementation is wrong in any sense, at least one test fails with probability > 0. more over, profile tests output performance stats for the target function. 
<<CUDA>>
+ inherit `<<CPP>>`
+ one table row per template instantiation, sweeping the whole parameter space the unit claims to support, seed varying per row
+ the unit test is driven on the smallest launch shape exhibiting the property; assert on host after `cudaDeviceSynchronize` and copy back, never inside a kernel
<<PYTHON>>
+ all tests live in `test_<module>.py` beside the module, collected by `pytest`
+ a test is named `test_<unit>_<property>` (correctness testing) or `prof_<unit>` (performance testing), and does not have to follow the naming convention for the production part
+ a test draws its inputs from `random.Random(seed)`, the seed a parameter swept by `pytest.mark.parametrize`
+ for each test, target a general property. tests should systematically eliminate classes of bugs, so we prefer fuzzing. when implementation is wrong in any sense, at least one test fails with probability > 0. more over, profile tests output performance stats for the target function.
