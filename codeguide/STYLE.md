# Style

To write a syntax item in production code, use the following convention:
+ **GENERAL**
    + Minimize caller obligation / context dependence:
        + For a given type, can all public methods of an object be called in any order under any concurrency?
        + If cannot, make the type system forbid such usage.
        + If cannot, panic loudly when things go wrong and make sure this obligation does not propagate through the system.
            + Wherever such obligation needs fulfilling, mark them into comment of both callee function and caller function.
    + Ensure unique path to every ident:
        + To publish a type/function/etc., either re-export through the super module or publish a submodule directly, never both.
+ **RUST**
    + file / module layout: 
        + `mod` name: one word, or two word `flatcase`
        + either export through `pub use` or `pub mod`, never both
    + module level declaration: 
        + `static` / `const` name should use 1 to 3 word `SNAKE_CAPITAL_CASE`
        + `fn` should use 1 to 3 word `flatcase`
    + type and type class: 
        + `struct` / `enum` / `trait` / `type` name : descriptive `CamelCase` with no word count limit
        + `struct` field name : 1 or 2 word `flatcase`; per struct, fields all same length
        + `enum` variant name : 1 or 2 word `CamelCase`; per enum, variants all same length
    + method and variables: 
        + `fn`: 1 or 2 word `flatcase`
        + `let`: 1 or 2 word `flatcase`
    + comment: 
        + always use `/// `, do not comment in function bodies; per block at most 60 words.
        + add literal tags in comments to functions more than 
            + 6 args `SHAME(MANYARG)`
            + 60 lines `SHAME(TALLFUNC)`
            + 120 chars `SHAME(WIDEFUNC)`
+ **TYPESCRIPT**
    + file / module layout: 
        + file name: `kebab-case.ts`
        + configure module resolution in each package: `folder` -> `folder/index.ts`
        + export through `export ... from { ... }`
        + only import from ancestors' direct siblings in folder tree
    + module level declaration:
        + `const` name : literal constant 1 to 3 words `CAPITAL_SNAKE`, otherwise 1 or 2 word `camelCase`
        + no global mutable state allowed, closure that captures other variables are also banned
    + type and type class: 
        + `type` / `interface` name : descriptive `CamelCase` with no word count limit
        + `type` / `interface` field name : 1 to 3 word `camelCase`; per struct, fields all same length
        + we don't use `class`, `this` is tricky in this language
    + method and variables: 
        + methods are added inside constructor functions `const newInterfaceName = (args: ...): InterfaceName => { ... }`
        + methods are defined as `function methodA(self: InterfaceName, ...): Type { ... }`, hooked into `interface { ..., methodA: (...) => Type }` by `newInterfaceName`
        + method names are 1 to 3 word `camelCase`
        + variable names are 1 to 3 word `camelCase`
    + comment: 
        + always use `/** */`, do not comment in function bodies, follow doxygen style
        + add literal tags in comments to functions more than 
            + 6 args `SHAME(MANYARG)`
            + 100 lines `SHAME(TALLFUNC)`
            + 120 chars `SHAME(WIDEFUNC)`
    + **Extension (TSX)**
        + file name (tsx): `ComponentName.tsx`
        + type name (tsx): `ComponentNameProps` 
        + props destructured in the signature, never read through one `props` binding
        + handler name : `onEventName` as a prop, rename to `handleEventName` during destructuring
        + state binding : `const [thing, setThing] = useState<T>(...)`, setter is the field name under a `set` prefix
    + **Extension (SVELTE)**
        + file name (svelte, svelte.ts): `ComponentName.svelte`, `kebab-case.svelte.ts`
        + type name (svelte): `ComponentNameProps`
        + props destructured in `let { ... }: ComponentNameProps = $props()`, never read through one `props` binding
        + handler name : `onEventName` as a prop, `handleEventName` in the body
+ **CPP**
    + file / module layout: 
        + file name: `src/flatcase.{cpp, cc, cxx}` and `include/flatcase.{hpp, hh, hxx}`
        + do not rely on transitive `#include`
        + `src/` and `include/` should have the same folder tree structure
    + module level declaration:
    + type and type class: 
        + `class` / `concept` name: descriptive `CamelCase` with no word count limit
        + `class` field name: 1 or 2 word `flatcase`; per class, fields all same length
        + `class` / `concept` method name: 1 to 2 word `flatcase`
        + in `class` block, only declare member fields and methods, leave definition outside
    + method and variables: 
    + comment: 
        + always use `/** */` before a function, follow doxygen style
        + use labels to comment like `// [1] ...`, `// [2] ...`, ...; each label is short pharse
        + add literal tags in comments to functions more than 
            + 6 args `SHAME(MANYARG)`
            + 100 lines `SHAME(TALLFUNC)`
            + 120 chars `SHAME(WIDEFUNC)`
    + **Extension (CUDA)**
        + file name (cu, cuh): `flatcase.{cu, cuh}`
        + comment: for each function, describe variable shape `@param [N, K] register`
+ **PYTHON**
    + file / module layout: 
        + file name: 
        + ...
    + ...

# Automated Unit Testing

+ **GENERAL**
    + Test 
    + Avoid tautology
        + Test written after implementation and passes immediately is garbage
        + Remove them immediately after you find such tests
+ **RUST (system internals style)**
    + for a file, test lines should be smaller than implementation code
    + `mod correct { ... }` sibling to tested `struct` for correctness
        + `#[test]` + `fn funcname() { ... }`
    + `mod profile { ... }` sibling to tested `struct` for performance
        + `#[test]` + `#[ignore]` + `fn funcname() { ... }`
+ **TYPESCRIPT**
+ **CPP**
+ **PYTHON**
