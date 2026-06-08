import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import App from "./App";

function mockSession(payload: object) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload,
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("landing page", () => {
  it("keeps the current homepage baseline", () => {
    mockSession({ authenticated: false });
    render(<App />);

    expect(screen.getByRole("heading", { name: "AI 图像生成" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "充值" })).toHaveAttribute("href", "/pricing");
    expect(screen.queryByRole("link", { name: "资产" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "管理后台" })).not.toBeInTheDocument();
  });

  it("opens login from the signed-out hero action and returns auth to the homepage", () => {
    mockSession({ authenticated: false });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /开始创作/ }));

    expect(screen.getByRole("dialog", { name: "登录绘世" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "登录绘世" })).toHaveAttribute("action", "/login?next=/");
    expect(screen.getByText("登录后留在首页，你可以再选择进入工作台或充值。")).toBeInTheDocument();
    expect(screen.queryByText("登录后进入工作台，继续生成和管理资产。")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开完整登录页面" })).toHaveAttribute(
      "href",
      "/login?next=/",
    );
  });

  it("returns register auth to the homepage", () => {
    mockSession({ authenticated: false });
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: /开始创作/ }));
    fireEvent.click(screen.getByRole("button", { name: "注册账号" }));

    expect(screen.getByRole("dialog", { name: "注册绘世" })).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "注册绘世" })).toHaveAttribute(
      "action",
      "/register?next=/",
    );
    expect(screen.getByText("创建账号后返回首页，并获得 20 点注册赠送。")).toBeInTheDocument();
    expect(screen.queryByText("创建账号后自动进入工作台，并获得 20 点注册赠送。")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开完整注册页面" })).toHaveAttribute(
      "href",
      "/register?next=/",
    );
  });

  it("shows workspace account and recharge navigation for authenticated users", async () => {
    mockSession({ authenticated: true, user: { username: "admin", role: "admin", points: 1000 } });
    render(<App />);

    await waitFor(() => expect(screen.getByRole("link", { name: "工作台" })).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "账户" })).toHaveAttribute("href", "/account");
    expect(screen.getAllByRole("link", { name: "充值" })[0]).toHaveAttribute("href", "/pricing");
    expect(screen.getByRole("link", { name: /开始创作/ })).toHaveAttribute("href", "/workspace");
  });
});
