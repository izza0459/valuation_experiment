CRM action button. One solid red primary per form (Proceed); everything else is soft pink, outline or tinted.
```jsx
<Button variant="outline">Cancel</Button>
<Button>Proceed</Button>
<Button variant="soft" icon={<Icon name="plus" size={16}/>}>Add Task</Button>
```
- Variants: primary, soft, outline, success (Create Flow), danger (Lost), ghost.
- Sizes sm 34 / md 42 / lg 46. `block` for full-width (lead Call button).