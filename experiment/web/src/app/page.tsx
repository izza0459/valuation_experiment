import { redirect } from "next/navigation";

// The app opens on the sign-in screen; after signing in it goes to /jobs.
export default function Home() {
  redirect("/login");
}
