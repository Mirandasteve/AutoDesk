import { Link } from 'react-router-dom'
import { useAsync } from '../../hooks/useAsync.js'
import { adminApi } from '../../services/api'
import { formatPercent } from '../../utils/format.jsx'
import {
  Alert,
  Card,
  DataTable,
  DetailList,
  DetailSkeleton,
  ErrorState,
  KeyValue,
  PageHeader,
  SkeletonStats,
  StatCard,
} from '../../components/ui.jsx'
import {
  ActivityIcon,
  AlertTriangleIcon,
  ArrowRightIcon,
  CpuIcon,
  DatabaseIcon,
  FileTextIcon,
  LayersIcon,
  RefreshIcon,
  TargetIcon,
} from '../../components/icons.jsx'

/**
 * ML status panel.
 *
 * This page exists to make the AI claim checkable: it reports whether the real
 * DistilBERT checkpoint is loaded, how many predictions the running server has
 * served, how many fell back to the keyword engine, and the held-out evaluation
 * metrics produced by `ml/evaluate.py`.
 */
export default function MlStatus() {
  const { data, loading, error, reload } = useAsync(() => adminApi.mlStatus(), [])

  if (loading) {
    return (
      <>
        <SkeletonStats />
        <div className="mt-6">
          <DetailSkeleton cards={[2]} />
        </div>
      </>
    )
  }
  if (error) return <ErrorState error={error} onRetry={reload} />

  const classifier = data?.classifier ?? {}
  const evaluation = data?.evaluation
  const routing = data?.routing_table ?? {}
  const training = data?.training

  const real = classifier.source === 'distilbert'
  const fallbackRate =
    classifier.predictions > 0
      ? ((classifier.fallback_predictions ?? 0) / classifier.predictions) * 100
      : 0

  return (
    <>
      <PageHeader
        eyebrow="Administration"
        title="Machine learning status"
        description="Live diagnostics for the classifier, the rule engines and the trained checkpoint."
        actions={
          <button type="button" className="btn-secondary" onClick={reload}>
            <RefreshIcon className="h-4 w-4" />
            Refresh
          </button>
        }
      />

      {!real && (
        <div className="mb-6">
          <Alert tone="danger" title="The real model is not loaded">
            The API is serving predictions from the keyword fallback
            {classifier.load_error ? `: ${classifier.load_error}` : '.'} Category results on screen
            are not DistilBERT output until the checkpoint loads.
          </Alert>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Engine"
          value={real ? 'DistilBERT' : 'Fallback'}
          tone={real ? 'success' : 'danger'}
          hint={classifier.source}
          icon={CpuIcon}
        />
        <StatCard
          label="Device"
          value={classifier.device ?? '—'}
          hint="CPU inference by default"
          icon={DatabaseIcon}
        />
        <StatCard
          label="Predictions served"
          value={classifier.predictions ?? 0}
          tone="brand"
          hint={`${classifier.fallback_predictions ?? 0} via fallback`}
          icon={ActivityIcon}
        />
        <StatCard
          label="Mean confidence"
          value={evaluation ? formatPercent(evaluation.mean_confidence) : '—'}
          hint="Held-out test split"
          icon={TargetIcon}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card title="Checkpoint" subtitle="What is actually loaded on this server" icon={CpuIcon}>
          <DetailList>
            <KeyValue label="Model name">{classifier.model}</KeyValue>
            <KeyValue label="Base model">{classifier.base_model}</KeyValue>
            <KeyValue label="Path" mono>
              {classifier.model_path}
            </KeyValue>
            <KeyValue label="Labels">{(classifier.labels ?? []).join(', ')}</KeyValue>
            <KeyValue label="Max sequence length">{classifier.max_length}</KeyValue>
            <KeyValue label="Fallback enabled">
              {classifier.allow_fallback ? 'yes' : 'no'}
            </KeyValue>
            <KeyValue label="Load error">
              {classifier.load_error ? (
                <span className="text-rose-600">{classifier.load_error}</span>
              ) : (
                'none'
              )}
            </KeyValue>
          </DetailList>

          <div className="panel mt-4">
            <p className="micro-label">Fallback usage this process</p>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-2xl font-semibold tracking-tight tabular-nums text-ink">
                {fallbackRate.toFixed(1)}%
              </span>
              <span className="text-xs text-ink-muted">
                of {classifier.predictions ?? 0} predictions
              </span>
            </div>
            <div className="mt-2.5 h-2 w-full overflow-hidden rounded-full bg-slate-200">
              <div
                className={`h-full rounded-full ${fallbackRate > 0 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                style={{ width: `${Math.max(2, Math.min(100, fallbackRate))}%` }}
              />
            </div>
          </div>
        </Card>

        <Card
          title="Evaluation report"
          subtitle={
            evaluation ? `Held-out split, ${evaluation.split_rows} rows` : 'No report available'
          }
          icon={FileTextIcon}
        >
          {evaluation ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <Metric label="Accuracy" value={evaluation.accuracy} tone="brand" />
                <Metric label="Macro F1" value={evaluation.macro_f1} tone="accent" />
                <Metric label="Weighted F1" value={evaluation.weighted_f1} tone="brand" />
                <Metric label="Misclassified" raw={evaluation.misclassified} tone="warning" />
              </div>

              <div className="mt-5">
                <p className="micro-label mb-2">Per-class breakdown</p>
                <div className="overflow-x-auto">
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">Class</th>
                        <th scope="col" className="text-right">
                          Precision
                        </th>
                        <th scope="col" className="text-right">
                          Recall
                        </th>
                        <th scope="col" className="text-right">
                          F1
                        </th>
                        <th scope="col" className="text-right">
                          Support
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(evaluation.per_class ?? {}).map(([label, stats]) => (
                        <tr key={label}>
                          <td className="font-semibold text-ink">{label}</td>
                          <td className="num">{stats.precision.toFixed(2)}</td>
                          <td className="num">{stats.recall.toFixed(2)}</td>
                          <td className="num">{stats.f1.toFixed(2)}</td>
                          <td className="num">{stats.support}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="panel mt-4">
                <p className="micro-label">Inference speed</p>
                <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-ink-soft">
                  {evaluation.inference_ms_per_ticket} ms per ticket on {evaluation.device} over{' '}
                  {evaluation.inference_seconds_total}s total &mdash; comfortably inside the SRS
                  three-second budget.
                </p>
              </div>

              {evaluation.macro_f1 === 1 && (
                <div className="mt-4">
                  <Alert tone="warning" title="About these metrics">
                    Perfect scores are expected here: the synthetic training corpus is generated
                    from per-category keyword templates, so the classes are highly separable. The
                    honest claim is that the pipeline works end to end on this data, not that
                    DistilBERT would score 100% on real production tickets.
                  </Alert>
                </div>
              )}
            </>
          ) : (
            <p className="text-sm text-ink-muted">
              No <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs">evaluation_report.json</code>{' '}
              was found next to the checkpoint.
            </p>
          )}
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card
          title="Routing table"
          subtitle="Category to support team, from the routing engine"
          icon={LayersIcon}
          bodyClass="p-0"
        >
          <DataTable
            columns={[
              {
                key: 'category',
                header: 'Category',
                cellClassName: 'font-semibold text-ink',
                render: ([category]) => category,
              },
              { key: 'team', header: 'Team', render: ([, team]) => team },
            ]}
            rows={Object.entries(routing)}
            rowKey={([category]) => category}
            dense
          />
        </Card>

        <Card
          title="Training history"
          subtitle="Read from training_history.json when present"
          icon={FileTextIcon}
        >
          {training ? (
            <pre className="max-h-80 overflow-auto rounded-xl bg-slate-900 p-4 font-mono text-xs leading-relaxed text-slate-100">
              {JSON.stringify(training, null, 2)}
            </pre>
          ) : (
            <div className="flex flex-col items-center gap-2 py-6 text-center">
              <AlertTriangleIcon className="h-6 w-6 text-ink-faint" />
              <p className="text-sm text-ink-muted">
                No training history file was saved with this checkpoint.
              </p>
            </div>
          )}
        </Card>
      </div>

      <p className="mt-6 text-xs text-ink-muted">
        Re-run the pipeline on any ticket from{' '}
        <Link
          to="/admin/tickets"
          className="inline-flex items-center gap-1 font-semibold text-brand-700 hover:underline"
        >
          All tickets
          <ArrowRightIcon className="h-3 w-3" />
        </Link>{' '}
        to verify the stored category is produced live.
      </p>
    </>
  )
}

/** Headline metric tile used inside the evaluation card. */
function Metric({ label, value, raw, tone = 'brand' }) {
  const accents = {
    brand: 'border-brand-200 bg-brand-50/60 text-brand-800',
    accent: 'border-accent-200 bg-accent-50/60 text-accent-800',
    warning: 'border-amber-200 bg-amber-50/60 text-amber-800',
  }
  return (
    <div className={`rounded-xl border p-3.5 ${accents[tone] ?? accents.brand}`}>
      <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] opacity-80">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold leading-none tracking-tight tabular-nums">
        {raw !== undefined ? raw : formatPercent(value)}
      </p>
    </div>
  )
}
