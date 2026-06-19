"use client";

import * as Select from "@radix-ui/react-select";
import React, { useState } from "react";

export type TerminalSelectOption = {
  value: string;
  label: string;
  disabled?: boolean;
  description?: string;
};

type TerminalSelectProps = {
  value: string;
  onValueChange: (value: string) => void;
  options: TerminalSelectOption[];
  placeholder?: string;
  disabled?: boolean;
  className?: string; // applied to Trigger
  contentClassName?: string; // applied to Content
  showSearch?: boolean;
};

export default function TerminalSelect({
  value,
  onValueChange,
  options,
  placeholder = "Select...",
  disabled = false,
  className,
  contentClassName,
  showSearch = false,
}: TerminalSelectProps) {
  const [open, setOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  const filteredOptions = showSearch
    ? options.filter(
        (opt) =>
          opt.label.toLowerCase().includes(searchTerm.toLowerCase()) ||
          opt.value.toLowerCase().includes(searchTerm.toLowerCase())
      )
    : options;

  return (
    <Select.Root
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
      open={open}
      onOpenChange={(isOpen) => {
        setOpen(isOpen);
        if (!isOpen) {
          setSearchTerm("");
        }
      }}
    >
      <Select.Trigger
        className={`h-7 form-input text-xs inline-flex items-center justify-between gap-2 select-none disabled:opacity-50 disabled:cursor-not-allowed ${className ?? ""}`}
        aria-label={placeholder}
      >
        <Select.Value placeholder={placeholder} />
        <Select.Icon className="text-[color:var(--text-muted)]">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M6 9l6 6 6-6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </Select.Icon>
      </Select.Trigger>

      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={6}
          className={`z-50 border border-[color:var(--border-subtle)] bg-[color:var(--surface-subtle)] text-[color:var(--text-primary)] shadow-none ${contentClassName ?? ""}`}
        >
          {showSearch && (
            <div className="p-1 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-raised)]">
              <input
                type="text"
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyDown={(e) => {
                  e.stopPropagation();
                }}
                className="w-full h-6 px-1.5 text-xs bg-[color:var(--surface-subtle)] border border-[color:var(--border-subtle)] text-[color:var(--text-primary)] focus:outline-none focus:border-[color:var(--border-strong)]"
              />
            </div>
          )}
          <Select.Viewport className="p-1 max-h-72 overflow-auto">
            {filteredOptions.length === 0 ? (
              <div className="text-[10px] text-[color:var(--text-muted)] px-2 py-1.5 select-none">
                No matching options
              </div>
            ) : (
              filteredOptions.map((opt) => (
                <Select.Item
                  key={opt.value}
                  value={opt.value}
                  disabled={opt.disabled}
                  title={opt.description}
                  className="text-xs px-2.5 py-2 outline-none select-none cursor-pointer data-[highlighted]:bg-[color:var(--surface-raised)] data-[highlighted]:text-[color:var(--text-primary)] data-[disabled]:opacity-40 data-[disabled]:cursor-not-allowed flex flex-col items-start gap-0.5 border-b border-[color:rgba(255,255,255,0.02)] last:border-b-0"
                >
                  <Select.ItemText className="font-semibold">{opt.label}</Select.ItemText>
                  {opt.description && (
                    <span className="text-[10px] text-[color:var(--text-muted)] leading-tight max-w-[280px] block">
                      {opt.description}
                    </span>
                  )}
                </Select.Item>
              ))
            )}
          </Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}
