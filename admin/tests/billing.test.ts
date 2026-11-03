import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { resetDbForTests } from '@/lib/db';
import { modelOf, openaiBill } from '@/lib/openai-billing';

const NOW = Date.parse('2026-11-03T00:37:00Z');
const at = (day: string) => Date.parse(`${day}T00:00:00Z`) / 1000;

const answer = (data: unknown[], more: object = {}) =>
  new Response(JSON.stringify({ data, has_more: false, ...more }), { status: 200 });

beforeEach(() => {
  process.env.ADMIN_DATA_DIR = 'memory://';
  process.env.OPENAI_ADMIN_KEY = 'test-key';
  delete process.env.DATABASE_URL;
  resetDbForTests();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  delete process.env.OPENAI_ADMIN_KEY;
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('line items', () => {
  it.each([
    ['gpt-realtime-2.1 audio, cached input', 'gpt-realtime-2.1'],
    ['gpt-realtime-2.1 image, input', 'gpt-realtime-2.1'],
    ['gpt-4.1-mini-2025-04-14, output', 'gpt-4.1-mini'],
    ['gpt-5.6-terra, cache writes', 'gpt-5.6-terra'],
    ['gpt-4o-mini-tts-2025-12-15 text, input', 'gpt-4o-mini-tts'],
    ['gpt-image-1 image, output', 'gpt-image-1'],
    ['gpt-transcribe', 'gpt-transcribe'],
    ['web search tool calls', 'web search tool calls'],
    [null, 'Other'],
  ])('%s is %s', (item, model) => {
    expect(modelOf(item)).toBe(model);
  });
});

describe('the bill', () => {
  it('is nothing without a key', async () => {
    delete process.env.OPENAI_ADMIN_KEY;
    expect(await openaiBill(NOW)).toBeNull();
  });

  it('gives each UTC day and model, and this month adds up only this month', async () => {
    const send = vi.fn(async () =>
      answer([
        {
          start_time: at('2026-10-30'),
          results: [{ amount: { value: 1 }, line_item: 'gpt-realtime-2.1 audio, output' }],
        },
        {
          start_time: at('2026-11-02'),
          results: [
            { amount: { value: 2 }, line_item: 'gpt-realtime-2.1 audio, output' },
            { amount: { value: 0.5 }, line_item: 'gpt-realtime-2.1 text, input' },
            { amount: { value: 0.1 }, line_item: 'gpt-5.6-terra, output' },
          ],
        },
        { start_time: at('2026-11-03'), results: [{ amount: { value: 0.0007 }, line_item: 'gpt-transcribe' }] },
      ]),
    );
    vi.stubGlobal('fetch', send);

    const bill = (await openaiBill(NOW))!;

    expect(bill.usd).toBeCloseTo(2.6007);
    expect(bill.days).toHaveLength(31);
    expect(bill.days.at(-1)?.day).toBe('2026-11-03');
    const second = bill.days.find((day) => day.day === '2026-11-02')!;
    expect(second.cost).toBeCloseTo(2.6);
    expect(second.models['gpt-realtime-2.1']).toBeCloseTo(2.5);
    expect(second.models['gpt-5.6-terra']).toBeCloseTo(0.1);
    expect(bill.days.find((day) => day.day === '2026-11-01')?.cost).toBe(0);

    const [url, options] = send.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain('/v1/organization/costs?');
    expect(url).toContain('group_by=line_item');
    expect(new URL(url).searchParams.get('start_time')).toBe(String(at('2026-10-04')));
    expect(options.headers).toEqual({ Authorization: 'Bearer test-key' });
  });

  it('reads every page', async () => {
    const send = vi
      .fn()
      .mockResolvedValueOnce(
        answer([{ start_time: at('2026-11-02'), results: [{ amount: { value: 1 }, line_item: 'a' }] }], {
          has_more: true,
          next_page: 'next',
        }),
      )
      .mockResolvedValueOnce(answer([{ start_time: at('2026-11-03'), results: [{ amount: { value: 2 }, line_item: 'b' }] }]));
    vi.stubGlobal('fetch', send);

    expect((await openaiBill(NOW))!.usd).toBeCloseTo(3);
    expect(String(send.mock.calls[1][0])).toContain('page=next');
  });

  it('asks again only after 15 minutes', async () => {
    const send = vi.fn(async () => answer([]));
    vi.stubGlobal('fetch', send);
    await openaiBill(NOW);
    await openaiBill(NOW + 14 * 60_000);
    expect(send).toHaveBeenCalledTimes(1);
    await openaiBill(NOW + 16 * 60_000);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('keeps and marks the last figures when OpenAI cannot be reached, and never logs the key', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => answer([{ start_time: at('2026-11-02'), results: [{ amount: { value: 5 }, line_item: 'a' }] }])),
    );
    await openaiBill(NOW);

    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 500 })));
    const later = (await openaiBill(NOW + 20 * 60_000))!;
    expect(later.stale).toBe(true);
    expect(later.usd).toBeCloseTo(5);
    expect(JSON.stringify(vi.mocked(console.error).mock.calls)).not.toContain('test-key');
  });

  it('is nothing when OpenAI refuses and there are no earlier figures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 401 })));
    expect(await openaiBill(NOW)).toBeNull();
  });

  it('a new month starts from zero', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => answer([{ start_time: at('2026-11-02'), results: [{ amount: { value: 5 }, line_item: 'a' }] }])),
    );
    expect((await openaiBill(Date.parse('2026-12-01T01:00:00Z')))!.usd).toBe(0);
  });
});
