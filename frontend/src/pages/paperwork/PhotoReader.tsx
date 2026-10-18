import { Button, Card, CardTitle, ErrorBox } from '../../components/ui'
import type { PhotoReader } from './usePhotoReader'

export function PhotoPicker({ r, label }: { r: PhotoReader; label: string }) {
  return (
    <Card>
      <CardTitle sub={r.file ? r.file.name : 'Example photo'}>The photo</CardTitle>
      <div className="overflow-hidden rounded-lg border border-line bg-subtle">
        <img src={r.preview} alt={label} className="max-h-[520px] w-full object-contain" />
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" loading={r.reading} disabled={!r.connected} onClick={r.read}>Read with Gemini</Button>
        <label className="inline-flex cursor-pointer items-center rounded-lg border border-line-strong bg-surface px-4 py-2 text-[14px] font-medium text-fg hover:bg-subtle">
          Upload a photo
          <input type="file" accept="image/*" className="hidden" onChange={(e) => r.setFile(e.target.files?.[0] ?? null)} />
        </label>
        <label className="inline-flex cursor-pointer items-center rounded-lg border border-line-strong bg-surface px-4 py-2 text-[14px] font-medium text-fg hover:bg-subtle sm:hidden">
          Take a photo
          <input type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => r.setFile(e.target.files?.[0] ?? null)} />
        </label>
        {r.file && <Button variant="ghost" onClick={() => r.setFile(null)}>Use the example</Button>}
      </div>
      {!r.connected && <div className="mt-3 text-[13px] text-fg-3">Reading photos needs a Gemini key, set in Settings.</div>}
      {r.error ? <div className="mt-3"><ErrorBox error={r.error} /></div> : null}
      {r.savedAt && <div className="mt-2 text-[12.5px] text-fg-4">Showing the last saved reading, from {r.savedAt}.</div>}
    </Card>
  )
}
