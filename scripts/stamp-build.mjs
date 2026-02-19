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
    hour: parts.hour,
    minute: parts.minute,
    second: parts.second,
    tz: tzName.replace(/\s+/g, ""),
  };
};

const updateBuildInfo = () => {
  const now = new Date();
  const parts = formatParts(now);
  const id = `${parts.year}-${parts.month}-${parts.day}-${parts.hour}${parts.minute}${parts.second}-${parts.tz}`;
  const label = `ThemeDeck Build ${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} ${parts.tz}`;
  const target = path.resolve("src/build-info.ts");
  const contents = `export const BUILD_LABEL = "${label}";\nexport const BUILD_ID = "${id}";\n`;
  fs.writeFileSync(target, contents, "utf-8");
  console.log(`Updated build label: ${label}`);
  console.log(`Build ID: ${id}`);
  return { id, label };
};

updateBuildInfo();
