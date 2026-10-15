76px white header: brand, CRM switcher, module nav (active = red text + red underline), round icon buttons, avatar.
```jsx
<TopNav items={[{label:'Dashboard'},{label:'Call Center',menu:true},{label:'Flows',menu:true}]} active="Flows" />
```
- No logo file was provided; pass `logo` with the real asset.