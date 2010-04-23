//
//  RootViewController.h
//  SocialGuidebook
//
//  Created by Naoki TSUTSUI on 10/04/24.
//  Copyright iphoneworld.jp 2010. All rights reserved.
//

@interface RootViewController : UITableViewController <NSFetchedResultsControllerDelegate> {
	NSFetchedResultsController *fetchedResultsController;
	NSManagedObjectContext *managedObjectContext;
}

@property (nonatomic, retain) NSFetchedResultsController *fetchedResultsController;
@property (nonatomic, retain) NSManagedObjectContext *managedObjectContext;

@end
