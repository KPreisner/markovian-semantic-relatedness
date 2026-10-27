"use client";

import { useEffect, useRef, useState } from "react";

import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import type { Term } from "@/lib/api";
import { api } from "@/lib/client/api";
import { formatCount } from "@/lib/format";

type Props = {
  modelId: string;
  value: string;
  onValueChange: (term: string) => void;
  /** A suggestion was chosen (click or Enter). */
  onPick?: (term: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
};

/** Term autocomplete over the model's vocab: case-sensitive prefix matches, most frequent first. */
export function TermCombobox({
  modelId,
  value,
  onValueChange,
  onPick,
  placeholder,
  autoFocus,
}: Props) {
  const [suggestions, setSuggestions] = useState<Term[]>([]);
  const [open, setOpen] = useState(false);
  const picked = useRef<string | null>(null);

  useEffect(() => {
    const prefix = value;
    if (!prefix || picked.current === prefix) {
      setSuggestions([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const terms = await api<Term[]>(
          `/models/${encodeURIComponent(modelId)}/terms?prefix=${encodeURIComponent(prefix)}&limit=8`,
          { signal: controller.signal },
        );
        setSuggestions(terms);
      } catch {
        setSuggestions([]);
      }
    }, 120);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [modelId, value]);

  const pick = (term: string) => {
    picked.current = term;
    onValueChange(term);
    onPick?.(term);
    setOpen(false);
  };

  return (
    <Command shouldFilter={false} className="relative overflow-visible bg-transparent p-0">
      <CommandInput
        value={value}
        onValueChange={(next) => {
          picked.current = null;
          onValueChange(next);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        placeholder={placeholder ?? "A term, e.g. trumpet"}
        autoFocus={autoFocus}
        className="font-mono text-base"
        aria-label="Chosen term"
      />
      {open && value && suggestions.length > 0 && (
        <CommandList className="absolute top-full z-50 mt-1 w-full rounded-xl border bg-popover p-1 shadow-xl">
          <CommandEmpty>No terms start with that.</CommandEmpty>
          {suggestions.map((s) => (
            <CommandItem
              key={s.term_idx}
              value={s.term}
              onSelect={pick}
              className="flex justify-between font-mono"
            >
              <span>{s.term}</span>
              <span className="tabular ml-auto text-xs text-muted-foreground">
                {formatCount(s.term_count)}
              </span>
            </CommandItem>
          ))}
        </CommandList>
      )}
    </Command>
  );
}
