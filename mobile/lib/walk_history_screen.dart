// A standalone "walk history" screen — a placeholder for now. Past walks will be
// populated once accounts land; until then it shows a clean empty state.

import 'package:flutter/material.dart';

import 'l10n/app_localizations.dart';

class WalkHistoryScreen extends StatelessWidget {
  const WalkHistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context)!;
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text(l.walkHistory)),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 36),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.route_rounded, size: 64, color: cs.onSurfaceVariant),
              const SizedBox(height: 18),
              Text(
                l.walkHistoryEmptyTitle,
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 8),
              Text(
                l.walkHistoryEmptySubtitle,
                style: TextStyle(fontSize: 14, height: 1.5, color: cs.onSurfaceVariant),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
