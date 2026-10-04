export class TurnQueue {
    private tails = new Map<string, Promise<void>>();

    run<T>(key: string, task: () => Promise<T>) {
        const previous = this.tails.get(key) || Promise.resolve();
        let release = () => {};
        const current = new Promise<void>((resolve) => {
            release = resolve;
        });
        const tail = previous.catch(() => undefined).then(() => current);
        this.tails.set(key, tail);

        return previous
            .catch(() => undefined)
            .then(task)
            .finally(() => {
                release();
                if (this.tails.get(key) === tail) this.tails.delete(key);
            });
    }
}
