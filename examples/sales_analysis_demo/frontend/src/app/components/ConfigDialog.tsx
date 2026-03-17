"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { StandaloneConfig } from "@/lib/config";

interface ConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (config: StandaloneConfig) => void;
  initialConfig?: StandaloneConfig;
}

export function ConfigDialog({
  open,
  onOpenChange,
  onSave,
  initialConfig,
}: ConfigDialogProps) {
  /** 本地 langgraph dev 默认值，与 backend/langgraph.json 中 graphs 的 key 一致 */
  const DEFAULT_DEPLOYMENT_URL = "http://127.0.0.1:2024";
  const DEFAULT_ASSISTANT_ID = "graph";

  const [deploymentUrl, setDeploymentUrl] = useState(
    initialConfig?.deploymentUrl || DEFAULT_DEPLOYMENT_URL
  );
  const [assistantId, setAssistantId] = useState(
    initialConfig?.assistantId || DEFAULT_ASSISTANT_ID
  );
  const [langsmithApiKey, setLangsmithApiKey] = useState(
    initialConfig?.langsmithApiKey || ""
  );

  useEffect(() => {
    if (open && initialConfig) {
      setDeploymentUrl(initialConfig.deploymentUrl);
      setAssistantId(initialConfig.assistantId);
      setLangsmithApiKey(initialConfig.langsmithApiKey || "");
    }
  }, [open, initialConfig]);

  const handleSave = () => {
    if (!deploymentUrl || !assistantId) {
      alert("Please fill in all required fields");
      return;
    }

    onSave({
      deploymentUrl,
      assistantId,
      langsmithApiKey: langsmithApiKey || undefined,
    });
    onOpenChange(false);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
    >
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>Configuration</DialogTitle>
          <DialogDescription>
            Configure your LangGraph deployment settings. These settings are
            saved in your browser&apos;s local storage. 本地开发时 Assistant ID 填
            &quot;graph&quot;（与 backend/langgraph.json 中 graphs 的 key 一致）。
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="deploymentUrl">Deployment URL</Label>
            <Input
              id="deploymentUrl"
              placeholder="http://127.0.0.1:2024"
              value={deploymentUrl}
              onChange={(e) => setDeploymentUrl(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="assistantId">Assistant ID</Label>
            <Input
              id="assistantId"
              placeholder="graph（本地）或 assistant UUID"
              value={assistantId}
              onChange={(e) => setAssistantId(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="langsmithApiKey">
              LangSmith API Key{" "}
              <span className="text-muted-foreground">(Optional)</span>
            </Label>
            <Input
              id="langsmithApiKey"
              type="password"
              placeholder="lsv2_pt_..."
              value={langsmithApiKey}
              onChange={(e) => setLangsmithApiKey(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Cancel
          </Button>
          <Button onClick={handleSave}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
