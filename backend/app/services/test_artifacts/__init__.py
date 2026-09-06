"""TestArtifact 领域服务分组（V2-P07）。

Artifact Domain ≠ agents/conversation。Agent/UI 未来必须经由同一 Application Service
写入，禁止绕过 Service 直接写 ORM/路由裸 add。
"""
