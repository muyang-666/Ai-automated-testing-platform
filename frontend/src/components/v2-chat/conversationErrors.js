const ERRORS = {
  configuration_not_ready: "Agent 对话模型尚未配置，请在模型管理中绑定模型。",
  insufficient_balance: "模型服务余额不足，请充值，或在模型管理中将“Agent 对话”切换到可用模型。",
  provider_auth_error: "模型服务认证失败，请在模型管理中检查 API Key 和访问权限。",
  provider_request_error: "模型服务拒绝了请求，请检查模型名称、参数或对话格式。",
  http_error: "模型服务拒绝了本轮请求，请检查模型账户余额、权限和配置。",
  network_error: "连接模型服务失败，请检查网络后重新发送。",
  deadline_exceeded: "模型响应超时，请稍后重新发送。",
  retryable_http: "模型服务暂时繁忙，重试后仍未成功，请稍后再试。",
  agent_runtime_error: "Agent 执行失败，请检查服务日志后重试。",
  model_error: "模型调用失败，请检查模型配置后重试。",
  canceled: "本轮回答已取消。",
};

export function runErrorMessage(code) {
  return ERRORS[code] || "本轮回答未完成，请稍后重新发送。";
}

export function messageFailure(message) {
  if (message.role !== "assistant") return null;
  if (message.stop_reason === "aborted") return ERRORS.canceled;
  if (message.stop_reason === "error") return runErrorMessage(message.error_code);
  return null;
}
