export interface AppConfig {
  pageTitle: string;
  pageDescription: string;
  companyName: string;

  supportsChatInput: boolean;
  supportsVideoInput: boolean;
  supportsScreenShare: boolean;
  isPreConnectBufferEnabled: boolean;

  logo: string;
  startButtonText: string;
  accent?: string;
  logoDark?: string;
  accentDark?: string;

  audioVisualizerType?: 'bar' | 'wave' | 'grid' | 'radial' | 'aura';
  audioVisualizerColor?: `#${string}`;
  audioVisualizerColorDark?: `#${string}`;
  audioVisualizerColorShift?: number;
  audioVisualizerBarCount?: number;
  audioVisualizerGridRowCount?: number;
  audioVisualizerGridColumnCount?: number;
  audioVisualizerRadialBarCount?: number;
  audioVisualizerRadialRadius?: number;
  audioVisualizerWaveLineWidth?: number;

  // agent dispatch configuration
  agentName?: string;

  // The shared web app for phones (PHONE_SITE_URL), whose link this PC's panel shows
  phoneSiteUrl?: string;

  // LiveKit Cloud Sandbox configuration
  sandboxId?: string;
}

export const APP_CONFIG_DEFAULTS: AppConfig = {
  companyName: 'HireAce',
  pageTitle: 'HireAce',
  pageDescription: 'HireAce voice assistant',

  supportsChatInput: true,
  // Off: the OpenAI voice brain does not take video (it reads the PC screen via tools)
  supportsVideoInput: false,
  supportsScreenShare: false,
  isPreConnectBufferEnabled: true,

  logo: '/hireace-logo.svg',
  accent: '#2f6bff',
  logoDark: '/hireace-logo.svg',
  accentDark: '#6b95ff',
  startButtonText: 'Talk to HireAce',

  // optional: audio visualization configuration
  // audioVisualizerType: 'bar',
  audioVisualizerColor: '#2f6bff',
  audioVisualizerColorDark: '#6b95ff',
  // audioVisualizerColorShift: 0.3,
  // audioVisualizerBarCount: 5,
  //audioVisualizerType: 'radial',
  //audioVisualizerRadialBarCount: 24,
  //audioVisualizerRadialRadius: 100,
  //audioVisualizerType: 'grid',
  //audioVisualizerGridRowCount: 25,
  //audioVisualizerGridColumnCount: 25,
  //audioVisualizerType: 'wave',
  //audioVisualizerWaveLineWidth: 3,
  // Bar visualizer: plain and light; the WebGL 'aura' shader was CPU/GPU heavy
  audioVisualizerType: 'bar',

  // agent dispatch configuration
  agentName: process.env.AGENT_NAME ?? undefined,

  // LiveKit Cloud Sandbox configuration
  sandboxId: undefined,
};
