#!/usr/bin/env node
import fs from "fs";
import path from "path";

const log = (message) => console.log(`[ThemeDeck] ${message}`);
const error = (message) => console.error(`[ThemeDeck] ${message}`);

const root = process.cwd();
const sourceDir = path.resolve(root, "dist");
const targetDir = path.resolve(root, "release", "ThemeDeck", "dist");
const pyModulesTargetDir = path.resolve(root, "release", "ThemeDeck", "py_modules");
const mainSource = path.resolve(root, "main.py");
const mainTarget = path.resolve(root, "release", "ThemeDeck", "main.py");

const ensureDir = (dir) => {
  fs.mkdirSync(dir, { recursive: true });
};

const removeRecursive = (target) => {
  if (!fs.existsSync(target)) {
    return;
  }
  const stats = fs.lstatSync(target);
  if (stats.isDirectory()) {
    for (const entry of fs.readdirSync(target)) {
      removeRecursive(path.join(target, entry));
    }
    fs.rmdirSync(target);
    return;
  }
  fs.unlinkSync(target);
};

const copyRecursive = (src, dest) => {
  const stats = fs.lstatSync(src);
  if (stats.isDirectory()) {
    ensureDir(dest);
    for (const entry of fs.readdirSync(src)) {
      copyRecursive(path.join(src, entry), path.join(dest, entry));
    }
    return;
  }
  ensureDir(path.dirname(dest));
  fs.copyFileSync(src, dest);
};

const syncDirectory = (src, dest, opts = {}) => {
  const required = opts.required ?? true;
  const cleanTarget = opts.cleanTarget ?? true;
  if (!fs.existsSync(src)) {
    if (required) {
      error(`Missing source directory: ${src}`);
      process.exit(1);
    }
    log(`Skipping missing optional source: ${src}`);
    return;
  }
  ensureDir(dest);
  if (cleanTarget) {
    for (const entry of fs.readdirSync(dest)) {
      removeRecursive(path.join(dest, entry));
    }
  }
  copyRecursive(src, dest);
  log(`Synced ${src} -> ${dest}`);
};

syncDirectory(sourceDir, targetDir, { required: true, cleanTarget: true });
copyRecursive(mainSource, mainTarget);
log(`Synced ${mainSource} -> ${mainTarget}`);
if (fs.existsSync(pyModulesTargetDir)) {
  removeRecursive(pyModulesTargetDir);
  log(`Removed ${pyModulesTargetDir}`);
}
