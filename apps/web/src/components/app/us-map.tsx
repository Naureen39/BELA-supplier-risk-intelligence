"use client";

import { useQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { STATES } from "@/lib/app/format";
import { ChartCard } from "./chart-card";

export interface MapPoint {
  name: string;
  lat: number;
  lon: number;
  value: number;
}

/** Choropleth of weighted event counts by state with facility events plotted by coordinates. No map tiles. */
export function UsMapCard({
  title,
  subtitle,
  states,
  points,
  demo,
}: {
  title: string;
  subtitle?: string;
  states: { state: string; value: number }[];
  points: MapPoint[];
  demo?: boolean;
}) {
  const geo = useQuery({
    queryKey: ["geo-us"],
    queryFn: () => fetch("/geo/us-states.json").then((r) => r.json()),
    staleTime: Infinity,
  });
  const setup = useCallback(
    (echarts: typeof import("echarts")) => {
      if (geo.data) echarts.registerMap("US", geo.data);
    },
    [geo.data],
  );
  const option = useMemo(() => {
    if (!geo.data) return undefined;
    const max = Math.max(1, ...states.map((s) => s.value));
    return {
      tooltip: {
        trigger: "item",
        formatter: (p: { name: string; value: number | number[]; seriesType: string }) =>
          p.seriesType === "scatter"
            ? `${p.name}`
            : `${p.name}: ${Array.isArray(p.value) ? "" : (p.value ?? 0)} weighted events`,
      },
      visualMap: {
        min: 0,
        max,
        left: 8,
        bottom: 8,
        text: ["More", "Fewer"],
        calculable: false,
        inRange: { color: ["#e6effb", "#2f74d8", "#12305a"] },
        textStyle: { color: "#64748b" },
      },
      geo: {
        map: "US",
        roam: false,
        aspectScale: 0.85,
        layoutCenter: ["50%", "52%"],
        layoutSize: "100%",
        itemStyle: { areaColor: "#f1f5f9", borderColor: "#94a3b8" },
        emphasis: { itemStyle: { areaColor: "#cfe0f7" }, label: { show: false } },
      },
      series: [
        {
          name: "Weighted events",
          type: "map",
          geoIndex: 0,
          data: states.map((s) => ({ name: STATES[s.state] ?? s.state, value: s.value })),
        },
        {
          name: "Facility events",
          type: "scatter",
          coordinateSystem: "geo",
          symbolSize: 9,
          itemStyle: { color: "#e69f00", borderColor: "#fff" },
          data: points.map((p) => ({ name: p.name, value: [p.lon, p.lat, p.value] })),
        },
      ],
    };
  }, [geo.data, states, points]);
  return (
    <ChartCard
      title={title}
      subtitle={subtitle}
      option={option}
      setup={setup}
      height={320}
      loading={geo.isLoading}
      error={geo.error}
      empty={!states.length && !points.length}
      demo={demo}
      filename="risk-by-state"
      table={{
        columns: ["State", "Weighted events"],
        rows: states.map((s) => ({
          State: STATES[s.state] ?? s.state,
          "Weighted events": s.value,
        })),
      }}
    />
  );
}
