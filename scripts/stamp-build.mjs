#!/usr/bin/env node
import fs from "fs";
import path from "path";

const TZ = "America/New_York";

const formatParts = (date) => {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  const parts = formatter.formatToParts(date).reduce(
    (acc, part) => ({
      ...acc,
      [part.type]: part.value,
    }),
    {}
  );

  const tzNameFormatter = new Intl.DateTimeFormat("en-US", {
    timeZone: TZ,
    timeZoneName: "short",
  });
  const tzName =
    tzNameFormatter
      .formatToParts(date)
      .find((part) => part.type === "timeZoneName")?.value ?? "ET";

  return {
    year: parts.year,
    month: parts.month,
    day: parts.day,
    // Some ICU versions report midnight as "24" with hour12: false.
    hour: String(Number(parts.hour) % 24).padStart(2, "0"),
    minute: parts.minute,
    second: parts.second,
    tz: tzName.replace(/\s+/g, ""),
  };
};

// ISO 8601 offset of the build timezone at that instant, e.g. "-05:00".
const offsetFor = (date, parts) => {
  const asUtc = Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour),
    Number(parts.minute),
    Number(parts.second)
  );
  const minutes = Math.round((asUtc - date.getTime()) / 60000);
  const pad = (value) => String(Math.abs(value)).padStart(2, "0");
  return `${minutes < 0 ? "-" : "+"}${pad(Math.trunc(minutes / 60))}:${pad(minutes % 60)}`;
};

const updateBuildInfo = () => {
  const now = new Date();
  const parts = formatParts(now);
  const id = `${parts.year}-${parts.month}-${parts.day}-${parts.hour}${parts.minute}${parts.second}-${parts.tz}`;
  const label = `ThemeDeck Build ${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} ${parts.tz}`;
  // Kept as a timezone-aware instant so the UI can render it in the user's locale.
  const time = `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}${offsetFor(now, parts)}`;
  const target = path.resolve("src/build-info.ts");
  const contents = `export const BUILD_LABEL = "${label}";\nexport const BUILD_ID = "${id}";\nexport const BUILD_TIME = "${time}";\n`;
  fs.writeFileSync(target, contents, "utf-8");
  console.log(`Updated build label: ${label}`);
  console.log(`Build ID: ${id}`);
  console.log(`Build time: ${time}`);
  return { id, label, time };
};

updateBuildInfo();
