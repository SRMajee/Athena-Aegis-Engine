'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useLogs } from '../context/LogContext';

const MIN_HEIGHT_PX = 28;   // just the header bar (collapsed)
const MAX_HEIGHT_PX = 600;
const DEFAULT_HEIGHT_PX = 220;

export default function LogDock() {
  const { logs, clearLogs } = useLogs();
  const [height, setHeight] = useState(DEFAULT_HEIGHT_PX);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const prevHeightRef = useRef(DEFAULT_HEIGHT_PX);
  const isDraggingRef = useRef(false);
  const dragStartYRef = useRef(0);
  const dragStartHeightRef = useRef(0);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new logs (only when not collapsed)
  useEffect(() => {
    if (!isCollapsed && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, isCollapsed]);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    dragStartYRef.current = e.clientY;
    dragStartHeightRef.current = height;
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
  }, [height]);

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!isDraggingRef.current) return;
      // Dragging up = increase height, dragging down = decrease height
      const delta = dragStartYRef.current - e.clientY;
      const newHeight = Math.max(MIN_HEIGHT_PX, Math.min(MAX_HEIGHT_PX, dragStartHeightRef.current + delta));
      setHeight(newHeight);
      if (newHeight <= MIN_HEIGHT_PX + 10) {
        setIsCollapsed(true);
      } else {
        setIsCollapsed(false);
        prevHeightRef.current = newHeight;
      }
    };
    const onMouseUp = () => {
      if (!isDraggingRef.current) return;
      isDraggingRef.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  const toggleCollapse = () => {
    if (isCollapsed) {
      const restoreHeight = prevHeightRef.current > MIN_HEIGHT_PX + 10 ? prevHeightRef.current : DEFAULT_HEIGHT_PX;
      setHeight(restoreHeight);
      setIsCollapsed(false);
    } else {
      prevHeightRef.current = height;
      setHeight(MIN_HEIGHT_PX);
      setIsCollapsed(true);
    }
  };

  return (
    <section
      style={{ height: `${height}px` }}
      className="border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-subtle)] text-[color:var(--text-primary)] flex flex-col overflow-hidden transition-none"
      aria-label="System logs"
    >
      {/* Drag handle */}
      <div
        onMouseDown={onMouseDown}
        className="h-[5px] w-full flex items-center justify-center cursor-ns-resize select-none shrink-0 group"
        style={{ backgroundColor: 'transparent' }}
        title="Drag to resize"
      >
        <div className="w-12 h-[3px] rounded-full bg-[color:var(--border-subtle)] group-hover:bg-[color:var(--border-strong)] transition-colors" />
      </div>

      {/* Header */}
      <div className="px-3 py-1 flex items-center justify-between text-[11px] uppercase tracking-wide border-b border-[color:var(--border-subtle)] shrink-0">
        <div
          className="flex items-center gap-2 cursor-pointer select-none"
          onClick={toggleCollapse}
          title={isCollapsed ? 'Expand logs' : 'Collapse logs'}
        >
          {/* Collapse chevron */}
          <span
            className="text-[color:var(--text-muted)] transition-transform duration-200"
            style={{ display: 'inline-block', transform: isCollapsed ? 'rotate(180deg)' : 'rotate(0deg)' }}
          >
            ▾
          </span>
          <span className="text-[color:var(--text-muted)]">System Logs</span>
          <span className="text-[color:var(--text-muted)]">
            {logs.length > 0 ? `${logs.length} lines` : 'idle'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void clearLogs()}
            className="h-6 px-2 border border-[color:var(--border-subtle)] text-[11px] text-[color:var(--text-soft)] hover:border-[color:var(--border-strong)] hover:bg-[color:var(--surface-raised)]"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Log body */}
      {!isCollapsed && (
        <div className="flex-1 px-3 py-2 overflow-auto log-terminal text-[color:var(--text-soft)] min-h-0">
          {logs.length === 0 ? (
            <span className="text-[color:var(--text-muted)]">Logs will appear here.</span>
          ) : (
            logs.map((line, i) => {
              const upper = line.toUpperCase();
              const levelClass =
                upper.includes(' ERROR ') || upper.startsWith('ERROR ') || upper.includes('| ERROR')
                  ? 'text-[color:var(--state-error)]'
                  : upper.includes(' WARN ') || upper.includes('| WARN') || upper.includes(' WARNING')
                    ? 'text-[color:var(--state-warning)]'
                    : 'text-[color:var(--text-soft)]';
              return (
                <div key={i} className={levelClass}>
                  {line}
                </div>
              );
            })
          )}
          <div ref={logsEndRef} />
        </div>
      )}
    </section>
  );
}
