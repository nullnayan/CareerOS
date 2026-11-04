import { Skeleton } from "./components/ui";

export default function Loading() {
  return (
    <div className="w-full animate-fade-in space-y-8">
      {/* Page heading */}
      <div className="space-y-2">
        <Skeleton className="h-9 w-[260px]" />
        <Skeleton className="h-4 w-[420px] max-w-[80vw]" />
      </div>

      {/* Stat row — hairline separated, not tiles */}
      <div className="grid grid-cols-2 gap-6 border-y border-rule py-5 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-7 w-14" />
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="space-y-3">
        <Skeleton className="h-4 w-[140px]" />
        {[0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    </div>
  );
}
