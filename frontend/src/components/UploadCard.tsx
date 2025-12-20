type Props = {
  loading: boolean
  onUpload: (file: File) => void
}

export default function UploadCard({ loading, onUpload }: Props) {
  return (
    <section className="card">
      <div className="card-title">Upload Wine Menu</div>
      <div className="card-subtitle">Upload 1 image (.jpg/.png). We will extract a wine list.</div>

      <label className="upload">
        <input
          type="file"
          accept="image/png,image/jpeg"
          disabled={loading}
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) onUpload(f)
            e.currentTarget.value = ''
          }}
        />
        <span className="upload-btn">{loading ? 'Analyzing…' : 'Upload Image'}</span>
      </label>

      <div className="upload-hint">Tip: a straight, well-lit photo works best.</div>
    </section>
  )
}
