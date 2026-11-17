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
