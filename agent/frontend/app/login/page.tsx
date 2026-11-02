import { cookies } from 'next/headers';
import { Button } from '@/components/ui/button';
import { LANGUAGE_COOKIE } from '@/lib/language';

const TEXT = {
  en: { label: 'Access code', enter: 'Continue', wrong: 'That code is not right. Try again.' },
  zh: { label: '访问码', enter: '继续', wrong: '访问码不正确，请重试。' },
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ wrong?: string }>;
}) {
  const language = (await cookies()).get(LANGUAGE_COOKIE)?.value === 'zh' ? 'zh' : 'en';
  const text = TEXT[language];
  const wrong = (await searchParams).wrong === '1';

  return (
    <main className="grid h-svh place-content-center px-4">
      <form method="post" action="/api/login" className="flex w-[min(92vw,20rem)] flex-col gap-3">
        <h1 className="text-lg font-semibold">HireAce</h1>
        <label htmlFor="code" className="text-muted-foreground text-sm">
          {text.label}
        </label>
        <input
          id="code"
          name="code"
          type="password"
          autoComplete="current-password"
          autoFocus
          required
          className="bg-background rounded-md border px-3 py-2 text-base"
        />
        {wrong && <p className="text-destructive text-sm">{text.wrong}</p>}
        <Button type="submit">{text.enter}</Button>
      </form>
    </main>
  );
}
