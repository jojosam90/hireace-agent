'use client';

import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { LANGUAGE_COOKIE, type Language } from '@/lib/language';

export type { Language };

const STRINGS = {
  en: {
    welcomeText: 'Talk to HireAce',
    startButton: 'Start',
    listening: 'HireAce is listening, ask a question',
    thinking: 'Thinking...',
    typeSomething: 'Type something...',
    send: 'Send',
    sending: 'Sending...',
    endCall: 'End call',
    controls: 'Voice assistant controls',
    toggleMicrophone: 'Toggle microphone',
    toggleCamera: 'Toggle camera',
    toggleScreenShare: 'Toggle screen share',
    toggleTranscript: 'Toggle transcript',
    selectMicrophone: 'Select a microphone',
    selectCamera: 'Select a camera',
    startAudio: 'Start Audio',
    sessionEnded: 'Session ended',
    callEnded: 'Call ended',
    agentEndedCall: 'HireAce ended the call.',
    connectionProblem: 'The connection was lost. Please start a new conversation.',
    pcNotAnswering: 'Your PC did not answer',
    pcNotAnsweringHelp:
      'Check that the PC is on and HireAce is running there (the HireAce icon on its desktop), then try again.',
    micLostTitle: 'HireAce can’t hear your microphone',
    micLostBody:
      'Your microphone stopped sending sound. Check your headset is plugged in, then end the call and start a new one.',
    fullView: 'Full view',
    mobileView: 'Mobile view',
    pcScreenButton: 'My PC',
    pcScreenTitle: 'HireAce on your PC',
    pcScreenConnecting: 'Connecting to your PC screen…',
    pcScreenUnavailable: 'Your PC screen is not available right now.',
    closePcScreen: 'Close',
    approvalHeading: 'HireAce wants to',
    approvalLabel: 'HireAce needs your approval',
    approve: 'Approve',
    deny: 'Deny',
    approvalCoversCall:
      'Approving lets HireAce control your computer for the rest of this call. Payments stay blocked.',
    actionClick: 'click “{target}”',
    actionType: 'type into “{target}”',
    actionOpen: 'open {url}',
    actionKey: 'press {key}',
    actionScreenClick: 'click on your PC screen',
    actionScreenType: 'type on your PC',
    actionScreenKey: 'press {keys} on your PC',
    actionCloseWindow: 'close the window “{title}”',
    actionOpenFile: 'open “{name}”',
    actionSendEmail: 'send the email “{subject}”',
    reasonSendEmail: 'The email goes out with the attached files.',
    actionSendQuotation: 'email the quotation to {to}',
    reasonSendQuotation:
      'It goes out as the reply to the inquiry, with the PDF from your Desktop. Check the PDF on screen first.',
    approvalThisEmailOnly: 'Asked for every quotation email.',
    actionSaveQuotation: 'save quotation {quote} as Excel and PDF',
    reasonSaveQuotation:
      'Check the draft in Excel first. Then it is saved, the PDF opens to preview and Excel closes.',
    approvalThisQuotationOnly: 'Asked for every quotation.',
    optionsLabel: 'Choose an option',
    emailSent: 'Email sent to {to}',
    openGmail: 'Open in Gmail',
    needPhoneLink:
      'To control your PC from this phone, open the phone link shown in the HireAce panel on your PC (or scan its QR code).',
    useFromPhone: 'Use from your phone',
    phoneLinkHelp:
      'Scan with your phone, or open this link on it. Keep HireAce running on this PC.',
    copyLink: 'Copy link',
    copied: 'Copied',
    reasonPassword: 'Typing into a password field.',
    reasonConsequential: 'This may have real consequences.',
    reasonOutsideBrowser: 'Uses your mouse or keyboard outside its browser.',
    reasonCloseWindow: 'Unsaved work in that window could be lost.',
    reasonMacros: 'This document can contain macros, which could run.',
    language: 'Language',
    languageLocked: 'End the call to switch language',
    themeToggle: 'Color scheme toggle',
    themeDark: 'Enable dark color scheme',
    themeLight: 'Enable light color scheme',
    themeSystem: 'Enable system color scheme',
    scrollToEnd: 'Scroll to end',
    scrollToStart: 'Scroll to start',
    gmailBarConnected: 'Gmail connected',
    gmailBarConnectedIn: 'Gmail connected: {where}',
    gmailBarNotConnected: 'Gmail not connected: open Gmail in Chrome or Edge',
    gmailBarUnknown: 'Cannot check Gmail right now',
    gmailBarGoTo: 'Go to the open Gmail',
    gmailBarNotFound: 'Gmail tab not found: open Gmail in Chrome or Edge',
    mirrorTitle: 'Live: conversation on your phone',
    mirrorWaiting: 'Waiting for the conversation…',
    settings: 'Settings',
    statusOnline: 'Online',
    statusConnecting: 'Connecting…',
    statusOffline: 'Offline: start HireAce on the PC',
    statusUnknown: 'Shows whether your PC is online once a call starts',
    settingsClose: 'Close settings',
    settingsPcOnly: 'Settings can only be changed on the PC itself.',
    settingsUnavailable: 'Settings are not available. Is HireAce running on this PC?',
    settingsSaved: 'Saved. New calls use these settings.',
    voiceLabel: 'HireAce’s voice',
  },
  zh: {
    welcomeText: '与 HireAce 对话',
    startButton: '开始对话',
    listening: 'HireAce 正在聆听，请提问',
    thinking: '思考中…',
    typeSomething: '输入消息…',
    send: '发送',
    sending: '发送中…',
    endCall: '结束通话',
    controls: '语音助手控制',
    toggleMicrophone: '开关麦克风',
    toggleCamera: '开关摄像头',
    toggleScreenShare: '开关屏幕共享',
    toggleTranscript: '显示/隐藏对话记录',
    selectMicrophone: '选择麦克风',
    selectCamera: '选择摄像头',
    startAudio: '开启音频',
    sessionEnded: '通话中断',
    callEnded: '通话已结束',
    agentEndedCall: 'HireAce 已结束本次通话。',
    connectionProblem: '连接已断开，请重新开始对话。',
    pcNotAnswering: '您的电脑没有应答',
    pcNotAnsweringHelp:
      '请确认电脑已开机，并且 HireAce 正在运行（电脑桌面上的 HireAce 图标），然后重试。',
    micLostTitle: 'HireAce 听不到您的麦克风',
    micLostBody: '您的麦克风已停止传送声音。请检查耳机是否已插好，然后结束通话并重新开始。',
    fullView: '全屏视图',
    mobileView: '手机视图',
    pcScreenButton: '我的电脑',
    pcScreenTitle: 'HireAce 正在操作您的电脑',
    pcScreenConnecting: '正在连接电脑屏幕…',
    pcScreenUnavailable: '暂时无法显示电脑屏幕。',
    closePcScreen: '关闭',
    approvalHeading: 'HireAce 想要',
    approvalLabel: 'HireAce 需要您的批准',
    approve: '批准',
    deny: '拒绝',
    approvalCoversCall: '批准后，HireAce 在本次通话中可以控制您的电脑，不再询问。付款始终被禁止。',
    actionClick: '点击“{target}”',
    actionType: '在“{target}”中输入',
    actionOpen: '打开 {url}',
    actionKey: '按下 {key}',
    actionScreenClick: '在您的电脑屏幕上点击',
    actionScreenType: '在您的电脑上输入',
    actionScreenKey: '在您的电脑上按下 {keys}',
    actionCloseWindow: '关闭窗口“{title}”',
    actionOpenFile: '打开“{name}”',
    actionSendEmail: '发送邮件“{subject}”',
    reasonSendEmail: '邮件将连同附件一起发送。',
    actionSendQuotation: '将报价单发送给 {to}',
    reasonSendQuotation:
      '报价单将作为询价邮件的回复发出，附上您桌面上的 PDF。请先查看屏幕上的 PDF。',
    approvalThisEmailOnly: '每封报价邮件都会询问。',
    actionSaveQuotation: '将报价单 {quote} 保存为 Excel 和 PDF',
    reasonSaveQuotation: '请先在 Excel 中检查草稿。保存后将打开 PDF 预览并关闭 Excel。',
    approvalThisQuotationOnly: '每份报价单都会询问。',
    optionsLabel: '请选择',
    emailSent: '邮件已发送至 {to}',
    openGmail: '在 Gmail 中打开',
    needPhoneLink:
      '要用这部手机控制您的电脑，请打开电脑上 HireAce 面板显示的手机链接（或扫描其二维码）。',
    useFromPhone: '在手机上使用',
    phoneLinkHelp: '用手机扫码，或在手机上打开此链接。请保持电脑上的 HireAce 运行。',
    copyLink: '复制链接',
    copied: '已复制',
    reasonPassword: '正在向密码框输入内容。',
    reasonConsequential: '此操作可能产生实际影响，需要您的确认。',
    reasonOutsideBrowser: '将在浏览器之外使用您的鼠标或键盘。',
    reasonCloseWindow: '该窗口中未保存的内容可能会丢失。',
    reasonMacros: '此文档可能包含宏，打开后宏可能会运行。',
    language: '语言',
    languageLocked: '结束通话后才能切换语言',
    themeToggle: '切换配色',
    themeDark: '使用深色模式',
    themeLight: '使用浅色模式',
    themeSystem: '跟随系统配色',
    scrollToEnd: '滚动到底部',
    scrollToStart: '滚动到顶部',
    gmailBarConnected: 'Gmail 已连接',
    gmailBarConnectedIn: 'Gmail 已连接：{where}',
    gmailBarNotConnected: 'Gmail 未连接：请在 Chrome 或 Edge 中打开 Gmail',
    gmailBarUnknown: '暂时无法检查 Gmail',
    gmailBarGoTo: '转到已打开的 Gmail',
    gmailBarNotFound: '找不到 Gmail 标签页：请在 Chrome 或 Edge 中打开 Gmail',
    mirrorTitle: '实时：手机上的对话',
    mirrorWaiting: '正在等待对话…',
    settings: '设置',
    statusOnline: '在线',
    statusConnecting: '正在连接…',
    statusOffline: '离线：请在电脑上启动 HireAce',
    statusUnknown: '通话开始后会显示电脑是否在线',
    settingsClose: '关闭设置',
    settingsPcOnly: '设置只能在电脑本机上更改。',
    settingsUnavailable: '无法打开设置。HireAce 是否正在这台电脑上运行？',
    settingsSaved: '已保存。新的通话将使用这些设置。',
    voiceLabel: 'HireAce 的声音',
  },
} as const;

export type StringKey = keyof (typeof STRINGS)['en'];

interface UiLanguageState {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: StringKey, vars?: Record<string, string>) => string;
}

const UiLanguageContext = createContext<UiLanguageState | null>(null);

export function UiLanguageProvider({
  initial,
  children,
}: {
  initial: Language;
  children: ReactNode;
}) {
  const [language, setLanguageState] = useState<Language>(initial);

  const setLanguage = useCallback((next: Language) => {
    // The token route reads this cookie to tell the agent which language to speak
    document.cookie = `${LANGUAGE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
    setLanguageState(next);
  }, []);

  // With the new text, not on the tap: it restyles the whole page
  useEffect(() => {
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  }, [language]);

  // Lay out the Chinese text once, off screen, while the page is idle: the first
  // time a browser draws Chinese characters is slow (about 0.4 s on a phone), and
  // that made the first switch to 中文 lag. Afterwards the browser has them cached.
  useEffect(() => {
    if (initial === 'zh' || typeof requestIdleCallback === 'undefined') return;
    const texts = Object.values(STRINGS.zh);
    let id = 0;
    const next = (index: number) => {
      if (index >= texts.length) return;
      id = requestIdleCallback(() => {
        const probe = document.createElement('div');
        probe.setAttribute('aria-hidden', 'true');
        probe.lang = 'zh-CN';
        probe.style.cssText = 'position:fixed;left:-10000px;top:0;width:320px;visibility:hidden';
        probe.textContent = texts[index];
        document.body.appendChild(probe);
        probe.getBoundingClientRect();
        probe.remove();
        next(index + 1);
      });
    };
    next(0);
    return () => cancelIdleCallback(id);
  }, [initial]);

  const t = useCallback(
    (key: StringKey, vars?: Record<string, string>) =>
      Object.entries(vars ?? {}).reduce<string>(
        (text, [name, value]) => text.replace(`{${name}}`, value),
        STRINGS[language][key]
      ),
    [language]
  );

  // Same object until the language changes: nothing re-renders for other reasons
  const value = useMemo(() => ({ language, setLanguage, t }), [language, setLanguage, t]);

  return <UiLanguageContext.Provider value={value}>{children}</UiLanguageContext.Provider>;
}

export function useUiLanguage(): UiLanguageState {
  const state = useContext(UiLanguageContext);
  if (!state) throw new Error('useUiLanguage must be used inside UiLanguageProvider');
  return state;
}
