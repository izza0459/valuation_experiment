import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex max-w-2xl flex-1 flex-col items-start justify-center gap-4 px-6">
      <h1 className="text-2xl font-semibold">Valuation Platform</h1>
      <p className="text-neutral-600">
        In-house real estate valuation platform for Dubizzle Group / Bayut. Replaces ValuePro.
      </p>
      <Link
        href="/jobs"
        className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
      >
        View jobs
      </Link>
    </main>
  );
}
