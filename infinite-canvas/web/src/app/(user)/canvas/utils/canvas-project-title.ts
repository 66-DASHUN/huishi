type ProjectTitleLike = {
    title?: string;
};

function escapeRegExp(value: string) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function nextCanvasProjectTitle(projects: ProjectTitleLike[], prefix: string) {
    const pattern = new RegExp(`^${escapeRegExp(prefix)}(?:\\s*(\\d+))?$`);
    const nextNumber =
        projects.reduce((max, project) => {
            const match = (project.title || "").trim().match(pattern);
            if (!match) return max;
            return Math.max(max, Number(match[1] || 1));
        }, 0) + 1;
    return `${prefix} ${nextNumber}`;
}
