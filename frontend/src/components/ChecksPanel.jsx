/* The consistency checks, as the analyst reads them.
 *
 * A failing blocking check is the most important thing on the screen, so it
 * is listed first and is the only element allowed to use red. A warning is
 * amber and does not shout: BR-08 says it must not stop anything, and an
 * interface that makes a warning look like a failure teaches the user to
 * ignore both.
 */

export default function ChecksPanel({ checks }) {
  if (!checks?.length) return null

  const ordered = [...checks].sort((a, b) => {
    const weight = (c) => (!c.passed && c.severity === 'BLOCKING' ? 0 : !c.passed ? 1 : 2)
    return weight(a) - weight(b)
  })

  return (
    <div className="card">
      <h2>Consistency checks</h2>
      <table>
        <tbody>
          {ordered.map((check) => (
            <tr key={check.code}>
              <td className="code" style={{ width: 80 }}>{check.code}</td>
              <td>
                {check.label}
                <div className="faint">{check.message}</div>
              </td>
              <td className="num" style={{ width: 120 }}>
                {/* The quantified discrepancy the dossier asks every check to
                    carry. "Out by 235" is actionable; "failed" is not. */}
                {check.gap !== null && check.gap !== undefined ? check.gap : ''}
              </td>
              <td style={{ width: 90, textAlign: 'right' }}>
                <span className={`pill ${check.passed ? 'ok' : check.severity === 'BLOCKING' ? 'fail' : 'warn'}`}>
                  {check.passed ? 'passed' : check.severity === 'BLOCKING' ? 'blocking' : 'warning'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
