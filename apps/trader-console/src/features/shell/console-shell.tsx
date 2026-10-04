"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import styles from "./console-shell.module.css";

const navigation = [
  { href: "/", label: "Connection", hint: "Environment status" },
  { href: "/data", label: "Market data", hint: "OHLCV exploration" },
  { href: "/backtests", label: "Backtest review", hint: "Inspect one run" },
  { href: "/backtests/new", label: "New backtest", hint: "Define and execute" },
  { href: "/comparisons", label: "Comparisons", hint: "Compare related runs" },
  { href: "/paper", label: "Paper operations", hint: "Runtime evidence" },
] as const;

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === href;
  if (href === "/backtests") return pathname === href;
  return pathname.startsWith(href);
}

export function ConsoleShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Trader Console navigation">
        <Link className={styles.brand} href="/" aria-label="Trader Console home">
          <span className={styles.mark} aria-hidden="true">T</span>
          <span>TRADER <span className={styles.brandSub}>/ Console</span></span>
        </Link>
        <nav className={styles.nav} aria-label="Primary">
          {navigation.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link className={`${styles.link} ${active ? styles.active : ""}`} href={item.href} aria-current={active ? "page" : undefined} key={item.href}>
                <span className={styles.linkLabel}>{item.label}</span>
                <span className={styles.hint}>{item.hint}</span>
              </Link>
            );
          })}
        </nav>
        <span className={styles.readOnly}>LOCAL SCOPE</span>
      </aside>
      <div className={styles.content}>{children}</div>
    </div>
  );
}
