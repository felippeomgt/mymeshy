import { useStore } from '../../store';
import { clamp01, relativeTime } from '../../utils';
import type { JobRecord } from '../../types';
import { jobTypeIcon, StopIcon } from '../Icons';

const TYPE_LABEL: Record<JobRecord['type'], string> = {
  text_to_3d: 'Text → 3D',
  image_to_3d: 'Image → 3D',
  texture: 'Texture',
};

function jobTitle(job: JobRecord): string {
  const prompt = job.params['prompt'];
  if (typeof prompt === 'string' && prompt.trim()) return prompt.trim();
  return TYPE_LABEL[job.type];
}

function JobItem({ job }: { job: JobRecord }) {
  const cancelJob = useStore((s) => s.cancelJob);
  const selectAsset = useStore((s) => s.selectAsset);
  const active = job.status === 'queued' || job.status === 'running';
  const pct = Math.round(clamp01(job.progress) * 100);

  return (
    <li
      className={`job job--${job.status} ${job.asset_id && job.status === 'done' ? 'job--clickable' : ''}`}
      onClick={() => {
        if (job.status === 'done' && job.asset_id) selectAsset(job.asset_id);
      }}
    >
      <div className="job__head">
        <span className="job__type" title={TYPE_LABEL[job.type]}>
          {jobTypeIcon(job.type)}
        </span>
        <span className="job__title" title={jobTitle(job)}>
          {jobTitle(job)}
        </span>
        <span className={`job__status job__status--${job.status}`}>{job.status}</span>
        {active && (
          <button
            className="icon-btn job__cancel"
            title="Cancel job"
            onClick={(e) => {
              e.stopPropagation();
              void cancelJob(job.id);
            }}
          >
            <StopIcon size={12} />
          </button>
        )}
      </div>

      {active && (
        <>
          <div className="job__bar">
            <div
              className={`job__bar-fill ${job.status === 'running' ? 'job__bar-fill--anim' : ''}`}
              style={{ width: `${job.status === 'queued' ? 0 : pct}%` }}
            />
          </div>
          <div className="job__stage">
            <span>{job.status === 'queued' ? 'Waiting in queue…' : job.stage || 'working…'}</span>
            <span className="job__pct">{job.status === 'running' ? `${pct}%` : ''}</span>
          </div>
          {job.message && <div className="job__message">{job.message}</div>}
        </>
      )}

      {job.status === 'error' && (
        <div className="job__error" title={job.error}>
          {job.error ?? 'Unknown error'}
        </div>
      )}

      <div className="job__meta">
        <span>{TYPE_LABEL[job.type]}</span>
        <span>{relativeTime(job.created_at)}</span>
      </div>
    </li>
  );
}

export function JobsList() {
  const jobs = useStore((s) => s.jobs);

  return (
    <section className="jobs">
      <header className="panel-subhead">
        <span>Jobs</span>
        {jobs.length > 0 && <span className="panel-subhead__count">{jobs.length}</span>}
      </header>
      {jobs.length === 0 ? (
        <div className="jobs__empty">No jobs yet — generate something above.</div>
      ) : (
        <ul className="jobs__list">
          {jobs.map((job) => (
            <JobItem key={job.id} job={job} />
          ))}
        </ul>
      )}
    </section>
  );
}
