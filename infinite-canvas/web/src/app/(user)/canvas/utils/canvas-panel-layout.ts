export function panelWidth(viewportWidth: number) {
    return Math.min(500, Math.max(280, viewportWidth - 24));
}
