import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useApiClient } from '@/api/context';
import { ApiError, type Job } from '@/api/types';
import { Button, Card, Field } from '@/components';
import { CheckIcon } from '@/icons';
import { WizardFrame } from './WizardFrame';

const API_ID = /^[a-z0-9][a-z0-9_-]*$/;

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function FileIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </svg>
  );
}

export function UploadStep() {
  const { apiId = 'new' } = useParams();
  const client = useApiClient();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const isNew = apiId === 'new';

  const [name, setName] = useState<string>(isNew ? 'New API' : apiId);
  const [job, setJob] = useState<Job | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [fields, setFields] = useState({ apiId: isNew ? '' : apiId, displayName: '', tag: '' });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isNew) return;
    const ctrl = new AbortController();
    client.getApi(apiId, ctrl.signal).then(
      (d) => setName(d.name.replace(/ API$/, '')),
      () => undefined, // the title falls back to the id; the upload itself still works
    );
    return () => ctrl.abort();
  }, [client, apiId, isNew]);

  const upload = useCallback(
    async (file: File) => {
      setUploading(true);
      setError(null);
      try {
        const created = await client.uploadPackage(file);
        setJob(created);
        setFields({
          apiId: isNew ? created.package.suggested.apiId : apiId,
          displayName: created.package.suggested.displayName,
          tag: created.package.suggested.tag,
        });
        if (!isNew) setName(created.package.suggested.displayName);
      } catch (e) {
        setJob(null);
        setError(
          e instanceof ApiError && e.status === 401
            ? 'Your session is not valid any more. Sign in again.'
            : e instanceof Error
              ? e.message
              : 'Upload failed.',
        );
      } finally {
        setUploading(false);
      }
    },
    [client, isNew, apiId],
  );

  function pick(files: FileList | null) {
    const file = files?.[0];
    if (file) void upload(file);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files);
  }

  const blockers = job?.package.validation.filter((c) => c.status === 'fail') ?? [];
  const idError =
    fields.apiId && !API_ID.test(fields.apiId)
      ? 'Use lowercase letters, digits, "-" or "_".'
      : null;
  const ready =
    job !== null &&
    blockers.length === 0 &&
    !idError &&
    fields.apiId !== '' &&
    fields.displayName.trim() !== '' &&
    fields.tag.trim() !== '';

  async function next(e: FormEvent) {
    e.preventDefault();
    if (!job || !ready) return;
    setSubmitting(true);
    setError(null);
    try {
      await client.reviewJob(job.id, {
        apiId: fields.apiId,
        displayName: fields.displayName.trim(),
        tag: fields.tag.trim(),
      });
      navigate(`/maintainer/jobs/${job.id}/review`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not review the package.');
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel() {
    if (job) await client.discardJob(job.id).catch(() => undefined);
    navigate('/maintainer');
  }

  return (
    <WizardFrame name={name} step={1}>
      <form className="two" onSubmit={next} noValidate>
        <Card className="pad">
          <h2 className="h2-sm">Package</h2>
          <div
            className={`drop${dragging ? ' over' : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <div className="file">
              <FileIcon />
            </div>
            <div className="drop-main">
              {job ? (
                <>
                  <b>{job.package.filename}</b>
                  <div className="muted small">
                    {formatSize(job.package.sizeBytes)} ·{' '}
                    {job.package.files.toLocaleString('en-US')} files
                  </div>
                </>
              ) : (
                <>
                  <b>{uploading ? 'Uploading and validating…' : 'Drop the package here'}</b>
                  <div className="muted small">
                    A .zip made by stream, up to the server size limit
                  </div>
                </>
              )}
            </div>
            <label className="btn ghost choose">
              <input
                ref={inputRef}
                type="file"
                accept=".zip,application/zip"
                className="sr-only"
                aria-label={job ? 'Replace package' : 'Choose package file'}
                onChange={(e) => {
                  pick(e.target.files);
                  e.target.value = '';
                }}
              />
              <span aria-hidden>{job ? 'Replace' : 'Choose file'}</span>
            </label>
          </div>
          <div className="grid3">
            <Field
              label="API id"
              mono
              value={fields.apiId}
              readOnly={!isNew}
              onChange={(e) => setFields({ ...fields, apiId: e.target.value })}
              hint={idError ?? 'Lowercase. Becomes the tag.'}
              aria-invalid={idError ? true : undefined}
              disabled={!job}
            />
            <Field
              label="Display name"
              value={fields.displayName}
              onChange={(e) => setFields({ ...fields, displayName: e.target.value })}
              disabled={!job}
            />
            <Field
              label="Version tag"
              mono
              value={fields.tag}
              onChange={(e) => setFields({ ...fields, tag: e.target.value })}
              disabled={!job}
            />
          </div>
          {uploading ? (
            <p role="status" className="muted small">
              Validating the package…
            </p>
          ) : null}
          {error ? (
            <p role="alert" className="form-error">
              {error}
            </p>
          ) : null}
        </Card>
        <Card className="pad">
          <h2 className="h2-sm">Validation</h2>
          {job ? (
            <ul className="checklist">
              {job.package.validation.map((c) => (
                <li key={c.key} className="check">
                  <span className={`ck ${c.status === 'ok' ? '' : c.status}`} aria-hidden>
                    <CheckIcon />
                  </span>
                  <div>
                    <div className="t">
                      {c.title}
                      <span className="sr-only">
                        {c.status === 'ok'
                          ? ' (passed)'
                          : c.status === 'warn'
                            ? ' (warnings)'
                            : ' (failed)'}
                      </span>
                    </div>
                    <div className="d">{c.detail}</div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Checks appear here once a package is chosen.</p>
          )}
        </Card>
        <div className="actions">
          <button type="button" className="linkbtn muted-link" onClick={() => void cancel()}>
            Cancel
          </button>
          <Button variant="primary" size="lg" type="submit" disabled={!ready || submitting}>
            Review changes →
          </Button>
        </div>
      </form>
      {isNew ? null : (
        <p className="sr-only">
          <Link to="/maintainer">Back to maintainer</Link>
        </p>
      )}
    </WizardFrame>
  );
}
