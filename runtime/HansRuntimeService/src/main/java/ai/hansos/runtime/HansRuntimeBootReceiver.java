package ai.hansos.runtime;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class HansRuntimeBootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        HansRuntimeService.applyV1DevicePolicy(context);
        context.startService(new Intent(context, HansRuntimeService.class));
        HansRuntimeService.launchCanvas(context);
    }
}
