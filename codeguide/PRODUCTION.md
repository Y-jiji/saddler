# Change Production Code

Confirmation is needed before a critical action:
+ a command **known or estimated** to be longer than 5 seconds
+ apply `Write/Edit/Bash` tool to edit production source code, i.e. git tracked code in the same folder that conatins **this** CLAUDE.md file

To get such confirmation, present your change skeleton and instructions to run, then literally present 'Say `sanction` to act'. 
Only act on last presented changes as a skeleton if the user says exact word 'sanction' or 'sanctioned'. 
Present markdown for skeleton directly in your response. 
+ Use file name or module path as section header, no need to wrap in `...`
    + The section body is exactly a code block
+ Use `+` for add and `-` for remove **right before target AST item** to indicate changes
    + Show full type/trait definitions. 
    + Fold function body, show function signature and the comment block for that function right before it. 
        + Apply `+` and `-` before the line to show the diff (even if it is not an AST item).  
    + Keep and follow original indentation. 
    + We show it for rust, but it should be the same for other language's AST item 
    ```rust
    fn oldfunc(+a: usize, b: usize) -> Type
    fn oldfunc(-a: usize, b: usize) -> Type
    +fn newfunc(a: usize, b: usize) -> Type
    -fn oldfunc(a: usize, b: usize) -> Type
    ```
    and
    ```rust
    struct A { +newfield: X, -oldfield: Y }
    enum B { +NewVariant, -OldVariant, OldVariantAlt(-X, Y) }
    ```

To inform user about change details, only answer what the user asked for and use a dedicated turn. 

To adjust the skeleton, present only the partial skeleton about files where skeleton adjust in a dedicated turn. 
However, full skeleton must be presented and sanctioned before changes happen. 

To fix an error that happens in a critical action, the fix needs a separate sanctioning. 

# Production Implementation Style

+ **GENERAL**
    + Minimize caller obligation / context dependence:
        + For a given type, can all public methods of an object be called in any order under any concurrency?
        + If cannot, make the type system forbid such usage.
        + If cannot, panic loudly when things go wrong and make sure this obligation does not propagate through the system.
            + Wherever such obligation needs fulfilling, mark them into comment of both callee function and caller function.
        + Caller should be able to use methods without preparation. 
    + Ensure unique path to every ident:
        + To publish a type/function/etc., either re-export through the super module or publish a submodule directly, never both.
    + Tag a function in the last line of its comment block, as `SADDLER: SHAME(MANYARG), ...`, for each limit it exceeds:
        + 6 args `SHAME(MANYARG)`
        + 60 lines for RUST / PYTHON, 100 lines for TYPESCRIPT / CPP `SHAME(TALLFUNC)`
        + 120 chars `SHAME(WIDEFUNC)`
+ **RUST**
    + file / module layout: 
        + `mod` name: one word, or two word `flatcase`
        + either export through `pub use` or `pub mod`, never both
    + module level declaration: 
        + `static` / `const` name should use 1 to 3 word `SNAKE_CAPITAL_CASE`
        + `fn` should use 1 to 3 word `flatcase`
    + type and type class: 
        + `struct` / `enum` / `trait` / `type` name : descriptive `CamelCase` with no word count limit
        + generics type should be abbrieved `CamelCase` like `Ty`
        + `struct` field name : 1 or 2 word `flatcase`; per struct, fields all same length
        + `enum` variant name : 1 or 2 word `CamelCase`; per enum, variants all same length
    + method and variables: 
        + `fn`: 1 or 2 word `flatcase`
        + `let`: 1 or 2 word `flatcase`
    + comment: 
        + always use `/// `, do not comment in function bodies; per block at most 60 words.
+ **TYPESCRIPT**
    + file / module layout: 
        + file name: `kebab-case.ts`
        + configure module resolution in each package: `folder` -> `folder/index.ts`
        + export through `export ... from { ... }`
        + only import from ancestors' direct siblings in folder tree
    + module level declaration:
        + `const` name : literal constant 1 to 3 words `CAPITAL_SNAKE`, otherwise 1 or 2 word `camelCase`
        + we do not allow globally mutable state including closure that captures other variables
    + type and type class: 
        + `type` / `interface` name : descriptive `CamelCase` with no word count limit
        + `type` / `interface` field name : 1 to 3 word `camelCase`; per struct, fields all same length
        + we don't use `class`. instead we define `export interface InterfaceName { ..., methodA: (...) => Type }`
            + use explicit function `export function newInterfaceName(...): InterfaceName { ... }`
            + implement methods as `function methodA(self: InterfaceName, ...): Type { ... }`, use `newInterfaceName` to mount it on creation. 
        + one exported `interface` per file / module
    + method and variables: 
        + method names are 1 to 3 word `camelCase`
        + variable names are 1 to 3 word `camelCase`
    + comment: 
        + always use `/** */`, do not comment in function bodies, follow doxygen style
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
        + `namespace` name: one word, or two word `flatcase`
        + constant name: 1 to 3 word `SNAKE_CAPITAL_CASE`, declared `constexpr`, `inline constexpr` in a header
        + free function name: 1 to 3 word `snake_case`
        + no mutable state at namespace scope or in `static` locals
        + helpers used only in one `src/` file go in an unnamed `namespace { ... }` there, never `static`
        + `#define` only where `constexpr` or a `template` cannot do it, named `SNAKE_CAPITAL_CASE` with the project name as first word
    + type and type class: 
        + `class` / `concept` name: descriptive `CamelCase` with no word count limit
        + `class` field name: 1 or 3 word `snake_case`; per class, fields all same length
        + `class` / `concept` method name: 1 to 3 word `snake_case`
        + in `class` block, only declare member fields and methods, leave definition outside
        + `template <typename Ty>` prefer `CamelCase` abbrievation
    + method and variables: 
    + comment: 
        + always use `/** */` before a function, follow doxygen style
        + use labels to comment like `// [1] ...`, `// [2] ...`, ... in a function body's top-level indent
    + **Extension (CUDA)**
        + file name (cu, cuh): `flatcase.{cu, cuh}`
        + comment (function): a kernel documents its index layout, not its arithmetic
+ **PYTHON**
    + file / module layout: 
        + managed by `uv`: `pyproject.toml` at the root, code in `src/<package>/`, commands exposed through `[project.scripts]`
        + file / package name: one word, or two word `flatcase`
        + either re-export through `__init__.py` or import the submodule directly, never both
    + module level declaration: 
        + constant name: 1 to 3 word `SNAKE_CAPITAL_CASE`, annotated `Final`
        + `def` name: 1 to 3 word `flatcase`
        + no module level mutable state
    + type and type class: 
        + `class` / `Protocol` / `TypedDict` / `Enum` / `dataclass` name: descriptive `CamelCase` with no word count limit
        + field name: 1 or 2 word `flatcase`; per class, fields all same length
        + `Enum` member name: 1 or 2 word `SNAKE_CAPITAL_CASE`; per enum, members all same length
    + method and variables: 
        + method name: 1 or 2 word `flatcase`
        + local / parameter name: 1 or 2 word `flatcase`
        + annotate every parameter and return, no bare `Any`
    + comment: 
        + always use `"""..."""` as the first statement of the item, do not comment in function bodies; per block at most 60 words

# Automated Unit Testing Style

+ **GENERAL**
    + Test from user perspective
        + Please only test what the user will use directly
        + Prefer pseudo random fuzz that utilizes all published methods
        + Test case should be much shorter than implementation
    + Avoid tautology
        + Test written after implementation and passes immediately is garbage
        + Remove them immediately after you find such tests
+ **RUST**
    + `#[cfg(test)] mod correct { ... }` sibling to tested `struct` for correctness
        + `#[test]` + `fn funcname() { ... }`
    + `#[cfg(test)] mod profile { ... }` sibling to tested `struct` for performance
        + `#[test]` + `#[ignore]` + `fn funcname() { ... }`
    + `#[cfg(test)] mod fixture { ... }` for test-only code shared by tests of multiple types or modules
+ **TYPESCRIPT**
    + place unit test in `*.test.ts` beside the tested file, for example `file.ts` -> `file.test.ts`
+ **CPP**
    + place all unittests in folder `PROJECT_ROOT/unittest/` besides `PROJECT_ROOT/src/`
        + make it available to `ctest` by `add_executable`, `add_test`
    + for correctness, write `unittest/test_[unit]_[property_name].cpp`
        + `main` returns 0 (success) or 1 (failure)
        + `main` runs a table of tests, print `[PASS]` / `[FAIL]` for each
    + for performance, write `unittest/prof_[unit]_[metric_name].cpp`
    + **Extension (CUDA)**
        + For correctness and performance, sweep all admissible shapes and all admissible template parameters
        + assert on the host after `cudaDeviceSynchronize`, never inside a kernel
+ **PYTHON**
    + place all unittests in folder `PROJECT_ROOT/unittest/` besides `PROJECT_ROOT/src/`
    + for correctness, write `unittest/test_*.py`, make it available to `python -m unittest`

