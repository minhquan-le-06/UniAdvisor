// The schools of a province with their khu vực ưu tiên, from the static file tools/build_school_areas.py writes. It is
// read in the browser and the student's school is not sent anywhere. Loaded once, on the first province chosen.
import { useEffect, useState } from "react";

export type School = { name: string; area: string };
type Table = Record<string, [string, string][]>;

let table: Promise<Table> | null = null;

function load(): Promise<Table> {
  if (!table) {
    table = fetch("/data/school-areas.json").then((r) => {
      if (!r.ok) throw new Error(String(r.status));
      return r.json() as Promise<Table>;
    });
    table.catch(() => { table = null; });          // a failed load can be tried again
  }
  return table;
}

export function useSchools(province: string | null): { schools: School[]; loading: boolean; error: boolean } {
  const [state, setState] = useState<{ province: string | null; schools: School[]; error: boolean }>({ province: null, schools: [], error: false });
  useEffect(() => {
    if (!province) return;
    let live = true;
    load().then(
      (t) => live && setState({ province, schools: (t[province] ?? []).map(([name, area]) => ({ name, area })), error: false }),
      () => live && setState({ province, schools: [], error: true }),
    );
    return () => { live = false; };
  }, [province]);
  const ready = !province || state.province === province;
  return { schools: ready && province ? state.schools : [], loading: !!province && !ready, error: ready && state.error };
}
