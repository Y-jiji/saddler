# Style

To write a syntax item in production code, use the following convention:
+ **RUST**
    + file name : one word, or two word `flatcase`
    + `static` / `const` name : one word or two word `SNAKE_CAPITAL_CASE`
    + `struct` / `enum` / `trait` / `type` name : normal `CamelCase`
        + `struct` field name : one word, or two word `flatcase`, per struct fields all same length
        + `enum` variant name : one word, or two word `CamelCase`, per enum variants all same length
    + `fn` / `let` / `mod` name : one word, or two word `flatcase`
    + `comment` : always use `/// `, do not comment in function bodies; per block at most 60 words.
    + `comment` : add literal tags in comments to functions more than 60 lines `SHAME(TALLFUNC)` / 120 chars `SHAME(WIDEFUNC)` / 6 args `SHAME(MANYARG)`
+ **TYPESCRIPT**
    + file name: `kebab-case.ts`
    + no module level mutable item, including internal mutablity
    + `const` name : literal constant one word or two word `SNAKE_CAPITAL_CASE`, otherwise one word or two word `camelCase`
    + `export const` / `export interface` / `export function` : use `export` on items directly
    + `interface` / `type` name : normal `CamelCase`
        + field name : one word, or two word `camelCase`
    + `class`: no `class`, use `interface X { ..., methodF(...): Y }` and `newX(): X` binds `function methodF(x: X, ...): Y` as `methodF(...): Y`
    + `function` / `let` name : one word, or two word `camelCase`
    + `comment` : always use `/** */` above the item, do not comment in function bodies; per block at most 60 words
    + `comment` : add literal tags in comments to functions more than 60 lines `SHAME(TALLFUNC)` / 120 chars `SHAME(WIDEFUNC)` / 6 args `SHAME(MANYARG)`
+ **TSX** (inherit **TYPESCRIPT**)
    + file name (tsx) : `ComponentX.tsx` (exports `ComponentX` and `ComponentXProps` only)
    + props type name : `<Component>Props`, destructured in the signature, never read through one `props` binding
    + handler name : `on<Event>` as a prop, rename to `handle<Event>` during destructuring
    + state binding : `const [thing, setThing] = useState<T>(...)`, setter is the field name under a `set` prefix
+ **SVELTE** (inherit **TYPESCRIPT**)
    + file name (svelte) : `CamelCase.svelte`, `kebab-case.svelte.ts`
    + props type name : `<Component>Props`, destructured in `let { ... }: <Component>Props = $props()`, never read through one `props` binding
    + handler name : `on<Event>` as a prop, `handle<Event>` in the body
+ **CPP**
    + file name : one word, or two word `flatcase.{cc,cxx,cpp,hh,hpp,hxx,...}`
    + `#define` / file scope `constexpr` / block scope compile time `constexpr` name : one word or two word `SNAKE_CAPITAL_CASE`, a macro carries its component as prefix
    + `class` / `struct` / `enum` name : normal `CamelCase`, a hardware prefix stays an acronym
        + field name : one word, or two word `flatcase`, same `struct` / `class` field names should have all same length
        + `enum` variant name : one word, or two word `SNAKE_CASE`, per enum variants all same length
    + no nested function body inside `class`
    + method / free function / local name : one word, or two word `flatcase`; a file scope free function is `static`
    + `template` parameter name : one word `SNAKE_CAPITAL_CASE`, a `bool` predicate parameter one word `flatcase`
    + `comment` : always use `/** @brief */` on the declaration, one line each for `@tparam` / `@param` / `@return`; in function bodies only numbered step markers `// [1]`; per block at most 60 words
    + `comment` : add literal tags in comments to functions more than 60 lines `SHAME(TALLFUNC)` / 100 chars `SHAME(WIDEFUNC)` / 6 args `SHAME(MANYARG)`
+ **CUDA** (inherit **CPP**)
    + `comment` : a kernel documents its index layout, not its arithmetic; the buffer order it maintains belongs in the `@class` block
+ **PYTHON**
    + file name : one word, or two word `flatcase.py`
    + no module level mutable
    + module level constant name : one word or two word `SNAKE_CAPITAL_CASE`, annotated `Final`
    + `class` / `Protocol` / `TypedDict` / `Enum` name : normal `CamelCase`
        + field name : one word, or two word `flatcase`, per class fields all same length
        + `Enum` member name : one word, or two word `SNAKE_CAPITAL_CASE`, per enum members all same length
    + `def` / local / parameter name : one word, or two word `flatcase`
    + every parameter and return annotated, no bare `Any`
    + `comment` : always use `"""..."""` as the first statement of the item, do not comment in function bodies; per block at most 60 words
    + `comment` : add literal tags in comments to functions more than 60 lines `SHAME(TALLFUNC)` / 120 chars `SHAME(WIDEFUNC)` / 6 args `SHAME(MANYARG)`

To write a correctness test for production code, follow listed conventions; test logic should be simpler than code; test is code, so it requires the same present + sanction process:
+ **RUST**
    + place `#[cfg(test)] mod correct` parallel to the tested object
    + place `#[test] fn ...() {...}` inside `mod correct`
    + if code is used to test multiple {type,module}'s behavior, place in `#[cfg(test)] mod fixture`
+ **TYPESCRIPT**
    + place `<file>.test.ts` beside `<file>.ts`
+ **TSX** (inherit **TYPESCRIPT**)
    + native: maesjtro + ts only tests with node
    + web: `<Component>.playwright.ts` besides `<Component>.tsx`
+ **SVELTE** (inherit **TYPESCRIPT**)
    + web: `<Component>.svelte` besides `<Component>.playwright.ts`
+ **CPP**
    + place `unittest/test_<...>.{cc,cpp,cxx}`, `main` function runs test suite, return error code (0 => success)
    + register in `CMakeLists.txt` by `add_executable` + `add_test`
+ **CUDA**
    + inherit **CPP**
    + sweep whole launch shape space, assert on host after `cudaDeviceSynchronize` and copy back, never inside a kernel
+ **PYTHON**
    + place `unittest/test_<...>.py`, use `class ...(unittest.TestCase):` for the test
