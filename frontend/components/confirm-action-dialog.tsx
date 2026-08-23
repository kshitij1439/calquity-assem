"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";

interface ActionProposal {
  action_type: string;
  draft_description: string;
  confirmation_token: string;
  expires_at: string;
}

interface ConfirmActionDialogProps {
  proposal: ActionProposal;
  onConfirm: (token: string) => void;
  onCancel: () => void;
}

const ACTION_TYPE_LABELS: Record<string, string> = {
  create_escalation: "Create Escalation",
  update_ticket: "Update Ticket",
  create_followup_task: "Create Follow-up Task",
};

export function ConfirmActionDialog({ proposal, onConfirm, onCancel }: ConfirmActionDialogProps) {
  const [confirming, setConfirming] = useState(false);

  const handleConfirm = async () => {
    setConfirming(true);
    await onConfirm(proposal.confirmation_token);
    setConfirming(false);
  };

  const expiresAt = new Date(proposal.expires_at).toLocaleTimeString();

  return (
    <Dialog open={true} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="bg-gray-900 border-gray-700 text-white max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-white">
            <span className="text-orange-400">⚠</span>
            Confirm Action Required
          </DialogTitle>
          <DialogDescription className="text-gray-400">
            The agent wants to perform a state-changing action. Review carefully before confirming.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="flex items-center gap-2">
            <span className="text-gray-400 text-sm">Action type:</span>
            <Badge className="bg-orange-900/60 text-orange-300 border-orange-700">
              {ACTION_TYPE_LABELS[proposal.action_type] ?? proposal.action_type}
            </Badge>
          </div>

          <div className="bg-gray-800/80 border border-gray-700 rounded-xl p-4">
            <p className="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">
              {proposal.draft_description}
            </p>
          </div>

          <div className="flex items-center gap-2 text-xs text-gray-500">
            <span>⏱</span>
            <span>This confirmation expires at {expiresAt}</span>
          </div>

          <div className="bg-red-950/30 border border-red-900/50 rounded-lg px-4 py-2.5 text-xs text-red-300">
            This action cannot be undone automatically. Once confirmed, it will be submitted to the system.
          </div>
        </div>

        <DialogFooter className="gap-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white border border-gray-700 hover:border-gray-500 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={confirming}
            className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white rounded-lg font-medium transition-colors"
          >
            {confirming ? "Confirming..." : "Confirm Action"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
