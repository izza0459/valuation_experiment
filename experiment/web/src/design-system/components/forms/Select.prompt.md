Native dropdown with the CRM filled-triangle caret; selected value shows in red, placeholder in grey.
```jsx
<Select placeholder="Select Payor" options={['Buyer','Seller']} value={v} onChange={e=>setV(e.target.value)} />
```