import { Suspense } from "react";
import { LoginForm } from "./LoginForm";

export default function LoginPage() {
  // useSearchParams (for ?next=) needs a Suspense boundary at build time.
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
