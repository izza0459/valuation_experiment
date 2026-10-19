import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./api";

export type Option = {
  /** A preset's stable key, or a record id for banks / users / templates. */
  value: string | number;
  label: string;
  /** Report paragraph a library entry inserts. */
  report_text?: string;
  /** Library entries: property categories it is offered for (empty = all). */
  categories?: string[];
  /** Banks: the bank's own code, which fills the Bank Reference No. */
  code?: string;
};

export type UserOption = Option & { roles: string[] };

/** Option lists keyed by the field config's `options_key`, plus `users`. */
export type OptionsMap = Record<string, Option[]> & { users: UserOption[] };

export function useOptions() {
  return useQuery({
    queryKey: ["options"],
    queryFn: () => apiFetch<OptionsMap>("/api/options/"),
    staleTime: 5 * 60 * 1000,
  });
}
