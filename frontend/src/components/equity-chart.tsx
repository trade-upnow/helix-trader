import { useTranslations } from "next-intl";

export function EquityChart() {
  const t = useTranslations("chart");

  return (
    <div className="glass-card grid-surface rounded-3xl p-5 md:p-6 flex flex-col justify-between">
      <style>{`
        @keyframes drawLine {
          from { stroke-dashoffset: 1000; }
          to { stroke-dashoffset: 0; }
        }
        @keyframes fadeFill {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes pulsePoint {
          0%, 100% { transform: scale(1); opacity: 0.8; }
          50% { transform: scale(1.5); opacity: 1; }
        }
        .animate-draw {
          stroke-dasharray: 1000;
          stroke-dashoffset: 1000;
          animation: drawLine 2.5s cubic-bezier(0.25, 1, 0.5, 1) forwards;
        }
        .animate-fill {
          opacity: 0;
          animation: fadeFill 1.5s ease-out 1s forwards;
        }
        .animate-point {
          opacity: 0;
          animation: fadeFill 0.5s ease-out forwards;
        }
        .pulse-circle {
          transform-origin: center;
          animation: pulsePoint 3s infinite ease-in-out;
        }
      `}</style>

      <div className="mb-4">
        <div className="flex items-center justify-between">
          <p className="text-sm uppercase tracking-[0.3em] text-cyan-300/80 font-medium">
            {t("title")}
          </p>
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <span className="text-xs text-emerald-400 font-medium uppercase tracking-wider">Live</span>
          </div>
        </div>
      </div>
      
      <div className="relative w-full flex-1 min-h-[160px] max-h-[220px]">
        <svg
          viewBox="0 0 600 200"
          className="absolute inset-0 h-full w-full overflow-visible"
          role="img"
          aria-label={t("title")}
          preserveAspectRatio="none"
        >
          <defs>
            <linearGradient id="equityLine" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#06b6d4" />
              <stop offset="50%" stopColor="#3b82f6" />
              <stop offset="100%" stopColor="#10b981" />
            </linearGradient>
            <linearGradient id="equityFill" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="rgba(16, 185, 129, 0.25)" />
              <stop offset="50%" stopColor="rgba(59, 130, 246, 0.1)" />
              <stop offset="100%" stopColor="rgba(6, 182, 212, 0.01)" />
            </linearGradient>
            <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Grid Background */}
          <g stroke="rgba(255,255,255,0.04)" strokeWidth="1">
            <line x1="0" y1="50" x2="600" y2="50" />
            <line x1="0" y1="100" x2="600" y2="100" />
            <line x1="0" y1="150" x2="600" y2="150" />
            <line x1="150" y1="0" x2="150" y2="200" strokeDasharray="4 4" />
            <line x1="300" y1="0" x2="300" y2="200" strokeDasharray="4 4" />
            <line x1="450" y1="0" x2="450" y2="200" strokeDasharray="4 4" />
          </g>

          {/* Area Fill */}
          <path
            className="animate-fill"
            d="M 0 180 L 30 175 L 60 165 L 90 170 L 120 140 L 150 145 L 180 130 L 210 115 L 240 120 L 270 95 L 300 80 L 330 85 L 360 65 L 390 50 L 420 60 L 450 45 L 480 50 L 510 35 L 540 30 L 570 35 L 600 20 L 600 200 L 0 200 Z"
            fill="url(#equityFill)"
          />

          {/* Main Line */}
          <path
            className="animate-draw"
            d="M 0 180 L 30 175 L 60 165 L 90 170 L 120 140 L 150 145 L 180 130 L 210 115 L 240 120 L 270 95 L 300 80 L 330 85 L 360 65 L 390 50 L 420 60 L 450 45 L 480 50 L 510 35 L 540 30 L 570 35 L 600 20"
            fill="none"
            stroke="url(#equityLine)"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            filter="url(#glow)"
          />

          {/* Highlight Points */}
          {[
            { x: 120, y: 140, color: "#10b981", delay: "0.8s" },
            { x: 270, y: 95, color: "#10b981", delay: "1.2s" },
            { x: 390, y: 50, color: "#10b981", delay: "1.6s" },
            { x: 420, y: 60, color: "#ef4444", delay: "1.8s" }, // small drawdown / stop
            { x: 600, y: 20, color: "#10b981", delay: "2.2s", pulse: true }, // current peak
          ].map((point, i) => (
            <g 
              key={i} 
              className="animate-point" 
              style={{ animationDelay: point.delay }}
            >
              {point.pulse && (
                <circle
                  className="pulse-circle"
                  cx={point.x}
                  cy={point.y}
                  r="6"
                  fill={point.color}
                  opacity="0.3"
                  style={{ transformOrigin: `${point.x}px ${point.y}px` }}
                />
              )}
              <circle
                cx={point.x}
                cy={point.y}
                r="3.5"
                fill="#0f172a"
                stroke={point.color}
                strokeWidth="2"
              />
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}
