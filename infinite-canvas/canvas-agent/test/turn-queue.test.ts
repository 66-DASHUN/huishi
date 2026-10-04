import assert from "node:assert/strict";
import test from "node:test";

import { TurnQueue } from "../src/turn-queue.js";

test("serializes turns for the same thread", async () => {
    const queue = new TurnQueue();
    const order: string[] = [];
    let releaseFirst = () => {};
    const firstGate = new Promise<void>((resolve) => {
        releaseFirst = resolve;
    });

    const first = queue.run("thread-a", async () => {
        order.push("first:start");
        await firstGate;
        order.push("first:end");
    });
    const second = queue.run("thread-a", async () => {
        order.push("second:start");
    });

    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.deepEqual(order, ["first:start"]);
    releaseFirst();
    await Promise.all([first, second]);
    assert.deepEqual(order, ["first:start", "first:end", "second:start"]);
});

test("allows different threads to run concurrently and recovers after failure", async () => {
    const queue = new TurnQueue();
    const order: string[] = [];
    let releaseA = () => {};
    const gateA = new Promise<void>((resolve) => {
        releaseA = resolve;
    });

    const threadA = queue.run("thread-a", async () => {
        order.push("a:start");
        await gateA;
    });
    await queue.run("thread-b", async () => {
        order.push("b:done");
    });
    assert.deepEqual(order, ["a:start", "b:done"]);
    releaseA();
    await threadA;

    await assert.rejects(() => queue.run("thread-a", async () => Promise.reject(new Error("failed"))), /failed/);
    await queue.run("thread-a", async () => {
        order.push("a:recovered");
    });
    assert.equal(order.at(-1), "a:recovered");
});
