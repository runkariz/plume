/** The link to a model or set: this site's origin plus the server's share path (the server may not know its public URL). */
export function shareLink(model: { id: string; sharePath?: string }): string {
  return `${window.location.origin}${model.sharePath ?? `/models/${model.id}`}`;
}
